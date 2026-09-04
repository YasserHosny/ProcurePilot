from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import psycopg
from postgrest.exceptions import APIError
from supabase import Client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.requests.schemas import (
    ApprovalStep,
    Money,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestLine,
    PurchaseRequestList,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
)
from procurepilot_api.modules.requests.valuation import (
    LineEstimate,
    estimate_line_value,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

REQUEST_COLUMNS = (
    "id,tenant_id,branch_id,cost_centre_id,requested_by_membership_id,"
    "required_by_date,status,estimated_total_amount,estimated_total_currency,"
    "has_incomplete_estimate,submitted_at,withdrawn_at,created_at,updated_at"
)
LINE_COLUMNS = (
    "id,purchase_request_id,workspace_product_id,quantity,note,"
    "estimated_unit_price_amount,estimated_unit_price_currency,"
    "estimated_unit_price_source_landed_cost_id,estimated_at"
)
STEP_COLUMNS = (
    "id,purchase_request_id,assigned_membership_id,source,status,"
    "comment,decided_by_membership_id,decided_at"
)

logger = logging.getLogger(__name__)


class RequestsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: PurchaseRequestCreate,
    ) -> PurchaseRequest:
        product_ids = [line.workspace_product_id for line in payload.lines]
        estimates = self._estimate_products(product_ids)
        quantities = [line.quantity for line in payload.lines]
        total_amount, total_currency, has_incomplete = _compute_totals(
            quantities, estimates
        )

        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("purchase_request")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "branch_id": str(payload.branch_id),
                        "cost_centre_id": (
                            str(payload.cost_centre_id)
                            if payload.cost_centre_id is not None
                            else None
                        ),
                        "requested_by_membership_id": str(member.membership_id),
                        "required_by_date": payload.required_by_date.isoformat(),
                        "status": "draft",
                        "estimated_total_amount": (
                            _format_decimal(total_amount, scale=4)
                            if total_amount is not None
                            else None
                        ),
                        "estimated_total_currency": total_currency,
                        "has_incomplete_estimate": has_incomplete,
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc

        request_row = _one_row(response.data, reason="request_write_failed")
        request_id = str(request_row["id"])

        line_rows = self._insert_lines(
            client,
            tenant_id=str(member.tenant_id),
            request_id=request_id,
            payload_lines=payload.lines,
            estimates=estimates,
        )

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_created",
            target={"purchase_request_id": request_id},
        )
        return _purchase_request(request_row, line_rows, step_row=None)

    def get_request(
        self,
        *,
        bearer_token: str,
        request_id: UUID,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)
        rid = str(request_id)
        line_rows = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)
        return _purchase_request(request_row, line_rows, step_row)

    def list_requests(
        self,
        *,
        bearer_token: str,
        status: PurchaseRequestStatus | None = None,
        branch_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> PurchaseRequestList:
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)

        try:
            query = client.table("purchase_request").select(REQUEST_COLUMNS)
            if status is not None:
                query = query.eq("status", status)
            if branch_id is not None:
                query = query.eq("branch_id", str(branch_id))
            response = (
                query.order("created_at", desc=True)
                .order("id")
                .range(offset, offset + capped)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc

        rows = _rows(response.data)
        visible = rows[:capped]
        next_cursor = (
            _encode_cursor(offset + capped) if len(rows) > capped else None
        )

        if not visible:
            return PurchaseRequestList(items=[], next_cursor=next_cursor)

        request_ids = [str(r["id"]) for r in visible]
        lines_by_request = self._fetch_lines_batch(client, request_ids)
        steps_by_request = self._fetch_steps_batch(client, request_ids)

        items = [
            _purchase_request(
                row,
                lines_by_request.get(str(row["id"]), []),
                steps_by_request.get(str(row["id"])),
            )
            for row in visible
        ]
        return PurchaseRequestList(items=items, next_cursor=next_cursor)

    def update_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        patch: PurchaseRequestUpdate,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._fetch_request(client, request_id)

        if str(existing["status"]) != "draft":
            raise ConflictError(details={"reason": "not_draft"})
        _require_requester(existing, member)

        updates: dict[str, object] = {}
        for field in ("branch_id", "cost_centre_id", "required_by_date"):
            if field not in patch.model_fields_set:
                continue
            val = getattr(patch, field)
            if isinstance(val, UUID):
                updates[field] = str(val)
            elif isinstance(val, date):
                updates[field] = val.isoformat()
            else:
                updates[field] = val

        new_line_rows: list[dict[str, object]] | None = None
        if patch.lines is not None:
            product_ids = [ln.workspace_product_id for ln in patch.lines]
            estimates = self._estimate_products(product_ids)
            quantities = [ln.quantity for ln in patch.lines]
            total_amount, total_currency, has_incomplete = _compute_totals(
                quantities, estimates
            )
            updates["estimated_total_amount"] = (
                _format_decimal(total_amount, scale=4)
                if total_amount is not None
                else None
            )
            updates["estimated_total_currency"] = total_currency
            updates["has_incomplete_estimate"] = has_incomplete

            try:
                client.table("purchase_request_line").delete().eq(
                    "purchase_request_id", str(request_id)
                ).execute()
            except APIError as exc:
                raise ServiceUnavailableError(
                    details={"dependency": "database"}
                ) from exc

            new_line_rows = self._insert_lines(
                client,
                tenant_id=str(member.tenant_id),
                request_id=str(request_id),
                payload_lines=patch.lines,
                estimates=estimates,
            )

        if updates:
            updates["updated_at"] = _now_iso()
            try:
                response = (
                    client.table("purchase_request")
                    .update(updates)
                    .eq("id", str(request_id))
                    .execute()
                )
            except APIError as exc:
                raise _write_error(exc) from exc
            request_row = _one_row_or_not_found(
                response.data, resource="purchase_request"
            )
        else:
            request_row = existing

        rid = str(request_id)
        if new_line_rows is None:
            new_line_rows = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_updated",
            target={"purchase_request_id": rid},
        )
        return _purchase_request(request_row, new_line_rows, step_row)

    def submit_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._fetch_request(client, request_id)

        if str(existing["status"]) != "draft":
            raise ConflictError(details={"reason": "not_draft"})
        _require_requester(existing, member)

        rid = str(request_id)
        line_rows = self._fetch_lines_for(client, rid)

        if not line_rows:
            raise UnprocessableEntityError(details={"reason": "no_lines"})

        product_ids = [
            UUID(str(lr["workspace_product_id"])) for lr in line_rows
        ]
        estimates = self._estimate_products(product_ids)

        now = _now_iso()
        for lr, est in zip(line_rows, estimates, strict=True):
            try:
                client.table("purchase_request_line").update(
                    {
                        "estimated_unit_price_amount": (
                            _format_decimal(est.unit_price_amount, scale=4)
                            if est.unit_price_amount is not None
                            else None
                        ),
                        "estimated_unit_price_currency": est.unit_price_currency,
                        "estimated_unit_price_source_landed_cost_id": (
                            str(est.source_landed_cost_id)
                            if est.source_landed_cost_id is not None
                            else None
                        ),
                        "estimated_at": now,
                    }
                ).eq("id", str(lr["id"])).execute()
            except APIError as exc:
                raise ServiceUnavailableError(
                    details={"dependency": "database"}
                ) from exc

        quantities = [_decimal(lr["quantity"], scale=6) for lr in line_rows]
        total_amount, total_currency, has_incomplete = _compute_totals(
            quantities, estimates
        )

        try:
            response = (
                client.table("purchase_request")
                .update(
                    {
                        "status": "submitted",
                        "submitted_at": now,
                        "estimated_total_amount": (
                            _format_decimal(total_amount, scale=4)
                            if total_amount is not None
                            else None
                        ),
                        "estimated_total_currency": total_currency,
                        "has_incomplete_estimate": has_incomplete,
                        "updated_at": now,
                    }
                )
                .eq("id", rid)
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc

        request_row = _one_row_or_not_found(
            response.data, resource="purchase_request"
        )
        frozen_lines = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_submitted",
            target={"purchase_request_id": rid},
        )
        return _purchase_request(request_row, frozen_lines, step_row)

    def withdraw_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._fetch_request(client, request_id)

        if str(existing["status"]) not in ("draft", "submitted"):
            raise ConflictError(
                details={"reason": "already_decided_or_withdrawn"}
            )
        _require_requester(existing, member)

        rid = str(request_id)
        now = _now_iso()
        try:
            response = (
                client.table("purchase_request")
                .update(
                    {
                        "status": "withdrawn",
                        "withdrawn_at": now,
                        "updated_at": now,
                    }
                )
                .eq("id", rid)
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc

        request_row = _one_row_or_not_found(
            response.data, resource="purchase_request"
        )
        line_rows = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_withdrawn",
            target={"purchase_request_id": rid},
        )
        return _purchase_request(request_row, line_rows, step_row)

    # ── internal helpers ──────────────────────────────────────────────

    def _estimate_products(self, product_ids: list[UUID]) -> list[LineEstimate]:
        db_url = self._settings.database_url.get_secret_value()
        with psycopg.connect(db_url) as conn:
            return [
                estimate_line_value(conn, workspace_product_id=pid)
                for pid in product_ids
            ]

    def _insert_lines(
        self,
        client: Client,
        *,
        tenant_id: str,
        request_id: str,
        payload_lines: list,
        estimates: list[LineEstimate],
    ) -> list[dict[str, object]]:
        inserts = [
            {
                "tenant_id": tenant_id,
                "purchase_request_id": request_id,
                "workspace_product_id": str(line.workspace_product_id),
                "quantity": line.quantity,
                "note": line.note,
                "estimated_unit_price_amount": (
                    _format_decimal(est.unit_price_amount, scale=4)
                    if est.unit_price_amount is not None
                    else None
                ),
                "estimated_unit_price_currency": est.unit_price_currency,
                "estimated_unit_price_source_landed_cost_id": (
                    str(est.source_landed_cost_id)
                    if est.source_landed_cost_id is not None
                    else None
                ),
            }
            for line, est in zip(payload_lines, estimates, strict=True)
        ]
        try:
            response = (
                client.table("purchase_request_line").insert(inserts).execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        return _rows(response.data)

    def _fetch_request(
        self, client: Client, request_id: UUID
    ) -> dict[str, object]:
        try:
            response = (
                client.table("purchase_request")
                .select(REQUEST_COLUMNS)
                .eq("id", str(request_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return _one_row_or_not_found(
            response.data, resource="purchase_request"
        )

    def _fetch_lines_for(
        self, client: Client, request_id: str
    ) -> list[dict[str, object]]:
        try:
            response = (
                client.table("purchase_request_line")
                .select(LINE_COLUMNS)
                .eq("purchase_request_id", request_id)
                .order("created_at")
                .order("id")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return _rows(response.data)

    def _fetch_lines_batch(
        self, client: Client, request_ids: list[str]
    ) -> dict[str, list[dict[str, object]]]:
        if not request_ids:
            return {}
        try:
            response = (
                client.table("purchase_request_line")
                .select(LINE_COLUMNS)
                .in_("purchase_request_id", request_ids)
                .order("created_at")
                .order("id")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        result: dict[str, list[dict[str, object]]] = {
            rid: [] for rid in request_ids
        }
        for row in _rows(response.data):
            rid = str(row["purchase_request_id"])
            if rid in result:
                result[rid].append(row)
        return result

    def _fetch_step(
        self, client: Client, request_id: str
    ) -> dict[str, object] | None:
        try:
            response = (
                client.table("approval_step")
                .select(STEP_COLUMNS)
                .eq("purchase_request_id", request_id)
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        rows = _rows(response.data)
        return rows[0] if rows else None

    def _fetch_steps_batch(
        self, client: Client, request_ids: list[str]
    ) -> dict[str, dict[str, object] | None]:
        if not request_ids:
            return {}
        try:
            response = (
                client.table("approval_step")
                .select(STEP_COLUMNS)
                .in_("purchase_request_id", request_ids)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        result: dict[str, dict[str, object] | None] = {
            rid: None for rid in request_ids
        }
        for row in _rows(response.data):
            rid = str(row["purchase_request_id"])
            if rid in result:
                result[rid] = row
        return result

    def _record(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        action: str,
        target: dict[str, object],
    ) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                target=target,
                outcome="success",
            ),
            bearer_token=bearer_token,
        )


def get_requests_service() -> RequestsService:
    return RequestsService()


# ── module-level helpers ──────────────────────────────────────────────


def _require_requester(
    request_row: dict[str, object], member: CurrentMember
) -> None:
    if str(request_row["requested_by_membership_id"]) != str(
        member.membership_id
    ):
        raise PermissionDeniedError(details={"reason": "not_requester"})


def _purchase_request(
    row: dict[str, object],
    line_rows: list[dict[str, object]],
    step_row: dict[str, object] | None,
) -> PurchaseRequest:
    return PurchaseRequest(
        id=UUID(str(row["id"])),
        branch_id=UUID(str(row["branch_id"])),
        cost_centre_id=(
            UUID(str(row["cost_centre_id"]))
            if row.get("cost_centre_id")
            else None
        ),
        requested_by_membership_id=UUID(
            str(row["requested_by_membership_id"])
        ),
        required_by_date=_parse_date(row["required_by_date"]),
        status=str(row["status"]),
        lines=[_purchase_request_line(lr) for lr in line_rows],
        estimated_total=_money(
            row.get("estimated_total_amount"),
            row.get("estimated_total_currency"),
        ),
        has_incomplete_estimate=bool(
            row.get("has_incomplete_estimate", False)
        ),
        budget_status=None,
        approval_step=_approval_step(step_row) if step_row else None,
        submitted_at=row.get("submitted_at"),
        withdrawn_at=row.get("withdrawn_at"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


def _purchase_request_line(row: dict[str, object]) -> PurchaseRequestLine:
    return PurchaseRequestLine(
        id=UUID(str(row["id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        quantity=_decimal(row["quantity"], scale=6),
        note=row.get("note"),
        estimated_unit_price=_money(
            row.get("estimated_unit_price_amount"),
            row.get("estimated_unit_price_currency"),
        ),
        estimated_unit_price_source_landed_cost_id=(
            UUID(str(row["estimated_unit_price_source_landed_cost_id"]))
            if row.get("estimated_unit_price_source_landed_cost_id")
            else None
        ),
    )


def _approval_step(row: dict[str, object]) -> ApprovalStep:
    return ApprovalStep(
        id=UUID(str(row["id"])),
        assigned_membership_id=UUID(str(row["assigned_membership_id"])),
        source=str(row["source"]),
        status=str(row["status"]),
        comment=row.get("comment"),
        decided_by_membership_id=(
            UUID(str(row["decided_by_membership_id"]))
            if row.get("decided_by_membership_id")
            else None
        ),
        decided_at=row.get("decided_at"),
    )


def _money(amount: object, currency: object) -> Money | None:
    if amount is None or currency is None:
        return None
    return Money(amount=_decimal(amount, scale=4), currency=str(currency))


def _compute_totals(
    quantities: list[str],
    estimates: list[LineEstimate],
) -> tuple[Decimal | None, str | None, bool]:
    currencies: set[str] = set()
    total = Decimal(0)
    any_missing = False

    for qty_str, est in zip(quantities, estimates, strict=True):
        if est.unit_price_amount is None:
            any_missing = True
            continue
        currencies.add(est.unit_price_currency)  # type: ignore[arg-type]
        total += Decimal(qty_str) * est.unit_price_amount

    mixed = len(currencies) > 1
    has_incomplete = any_missing or mixed

    if len(currencies) == 1:
        return total, currencies.pop(), has_incomplete
    return None, None, has_incomplete


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _decimal(value: object, *, scale: int) -> str:
    exponent = Decimal(10) ** -scale
    return format(Decimal(str(value)).quantize(exponent), "f")


def _format_decimal(value: Decimal, *, scale: int) -> str:
    exponent = Decimal(10) ** -scale
    return format(value.quantize(exponent), "f")


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ServiceUnavailableError(details={"reason": "invalid_date"})


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _one_row(data: object, *, reason: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": reason})
    return rows[0]


def _one_row_or_not_found(
    data: object, *, resource: str
) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(
            details={"reason": f"{resource}_write_ambiguous"}
        )
    return rows[0]


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        offset = payload["offset"]
    except (
        KeyError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise UnprocessableEntityError(
            details={"cursor": "invalid"}
        ) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset


def _write_error(
    exc: APIError,
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    code = _api_error_code(exc)
    if code in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(
            details={"reason": "database_constraint"}
        )
    if code == "23505":
        return ConflictError(details={"reason": "duplicate"})
    return ServiceUnavailableError(details={"dependency": "database"})


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None
