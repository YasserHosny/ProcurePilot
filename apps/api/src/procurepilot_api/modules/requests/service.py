from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID, uuid4

import psycopg
from postgrest.exceptions import APIError
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from supabase import Client

from procurepilot_api import db
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.devices.push_job import enqueue_push_job
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.orders.vat_split import net_unit_price
from procurepilot_api.modules.requests.budget_status import (
    BudgetRow,
    SpendRow,
    budget_period_end,
    compute_budget_status,
)
from procurepilot_api.modules.requests.routing import (
    DelegationRow,
    ThresholdRuleRow,
    resolve_approver,
)
from procurepilot_api.modules.requests.schemas import (
    TERMINAL_REQUEST_STATUSES,
    ApprovalDecisionInput,
    ApprovalDelegation,
    ApprovalDelegationCreate,
    ApprovalDelegationList,
    ApprovalStep,
    AutoPreparedProvenance,
    BudgetStatus,
    DeliveryConfirmationCreate,
    LowStockReport,
    LowStockReportCreate,
    LowStockReportList,
    Money,
    PendingApprovalList,
    PendingApprovalSort,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestLine,
    PurchaseRequestLineInput,
    PurchaseRequestList,
    PurchaseRequestSort,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
    QualityIssue,
    QualityIssueCreate,
    QualityIssueList,
    QualityIssuePhoto,
    RequestGroupSibling,
    RequestGroupSummary,
    RequestSource,
    ThresholdRule,
    ThresholdRuleCreate,
    ThresholdRuleList,
    ThresholdRuleUpdate,
)
from procurepilot_api.modules.requests.valuation import (
    LineEstimate,
    QuotedPrice,
    estimate_from_source_quotation,
    estimate_from_source_response,
    estimate_line_value,
    quoted_prices_from_source_response,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.storage_keys import safe_object_name

REQUEST_COLUMNS = (
    "id,tenant_id,branch_id,cost_centre_id,requested_by_membership_id,"
    "required_by_date,status,request_group_id,source_rfq_response_id,source_rfq_id,source_quotation_id,"
    "source_supplier_id,estimated_total_amount,estimated_total_currency,"
    "has_incomplete_estimate,submitted_at,withdrawn_at,delivered_at,"
    "delivery_confirmed_by_membership_id,has_delivery_discrepancy,"
    "created_at,updated_at"
)
LINE_COLUMNS = (
    "id,purchase_request_id,workspace_product_id,quantity,note,"
    "quantity_received,pack_base_quantity,"
    "estimated_unit_price_amount,estimated_unit_price_currency,"
    "estimated_unit_price_source_landed_cost_id,estimated_at"
)
STEP_COLUMNS = (
    "id,purchase_request_id,assigned_membership_id,source,status,"
    "comment,decided_by_membership_id,decided_at"
)
GROUP_TOTAL_COLUMNS = (
    "rfq_id,combined_total_amount,combined_total_currency,"
    "best_single_total_amount,best_single_total_currency,saving_amount,saving_currency"
)


# A request can become a purchase order only while its own status still says it is approved;
# an approved step alone is not enough once the request is withdrawn or rejected afterwards.
ORDERABLE_REQUEST_STATUSES = ("approved", "ordered")


def orderable_request_predicate(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    statuses = ", ".join(f"'{status}'" for status in ORDERABLE_REQUEST_STATUSES)
    return f"{prefix}status in ({statuses})"


def approved_step_predicate(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        f"{prefix}status = 'approved' and {prefix}decided_by_membership_id is not null "
        f"and {prefix}decided_at is not null"
    )


THRESHOLD_RULE_COLUMNS = (
    "id,branch_id,min_amount,max_amount,currency,approver_membership_id,"
    "created_by,created_at,updated_at"
)
DELEGATION_COLUMNS = (
    "id,delegator_membership_id,delegate_membership_id,starts_on,ends_on,created_at"
)
BUDGET_COLUMNS = "id,amount,currency,period,period_start,scope,branch_id,cost_centre_id"
# Statuses whose estimate counts against a budget. An approved request stays "approved" until a
# live purchase order moves it to "ordered" (ADR-025), later "delivered"; approved, ordered and
# delivered all count as committed spend (draft, rejected and withdrawn do not).
COMMITTED_SPEND_STATUSES = ("submitted", "approved", "ordered", "delivered")
# Matches the Data API max_rows (supabase/config.toml); a full page means "fetch the next".
COMMITTED_SPEND_PAGE_SIZE = 1000
QUALITY_ISSUE_COLUMNS = (
    "id,tenant_id,purchase_request_id,reported_by_membership_id,description,created_at"
)
QUALITY_ISSUE_PHOTO_COLUMNS = "id,tenant_id,delivery_quality_issue_id,storage_path,created_at"

logger = logging.getLogger(__name__)


class MemberContact(NamedTuple):
    """How a member is shown on a request: their name when set (PPS-125), and their email."""

    email: str | None
    name: str | None


class RequestsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _validate_request_lines(self, lines: Sequence[PurchaseRequestLineInput]) -> None:
        seen: set[UUID] = set()
        for i, line in enumerate(lines):
            if line.note is not None and len(line.note.strip()) > 500:
                raise UnprocessableEntityError(
                    details={"field": f"lines[{i}].note", "reason": "note_too_long"}
                )
            try:
                qty = Decimal(str(line.quantity))
            except Exception:
                raise UnprocessableEntityError(
                    details={"field": f"lines[{i}].quantity", "reason": "quantity_not_positive"}
                ) from None
            if qty <= Decimal("0") or qty.as_tuple().exponent < -6:
                raise UnprocessableEntityError(
                    details={"field": f"lines[{i}].quantity", "reason": "quantity_not_positive"}
                )
            if line.workspace_product_id in seen:
                raise UnprocessableEntityError(
                    details={
                        "field": f"lines[{i}].workspace_product_id",
                        "reason": "duplicate_product",
                    }
                )
            seen.add(line.workspace_product_id)

    def _validate_required_by_date(self, req_date: date) -> None:
        if req_date < datetime.now(UTC).date():
            raise UnprocessableEntityError(
                details={"field": "required_by_date", "reason": "required_by_in_the_past"}
            )

    def _validate_products_exist(
        self, client: Client, *, lines: Sequence[PurchaseRequestLineInput]
    ) -> None:
        product_ids = [str(line.workspace_product_id) for line in lines]
        if not product_ids:
            return
        try:
            response = (
                client.table("workspace_product")
                .select("id")
                .in_("id", list(dict.fromkeys(product_ids)))
                .execute()
            )
            found_ids = {str(row["id"]) for row in (response.data or [])}
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        for i, line in enumerate(lines):
            if str(line.workspace_product_id) not in found_ids:
                raise UnprocessableEntityError(
                    details={
                        "field": f"lines[{i}].workspace_product_id",
                        "reason": "product_not_found",
                    }
                )

    def _validate_cost_centre_branch(
        self, client: Client, *, cost_centre_id: UUID, branch_id: UUID
    ) -> None:
        try:
            response = (
                client.table("cost_centre")
                .select("id,branch_id")
                .eq("id", str(cost_centre_id))
                .execute()
            )
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if not response.data:
            raise UnprocessableEntityError(
                details={"field": "cost_centre_id", "reason": "cost_centre_not_found"}
            )
        cc = response.data[0]
        cc_branch_id = cc.get("branch_id")
        if cc_branch_id is not None and str(cc_branch_id) != str(branch_id):
            raise UnprocessableEntityError(
                details={"field": "cost_centre_id", "reason": "cost_centre_branch_mismatch"}
            )

    def _insert_lines_db(
        self, cur: psycopg.Cursor, *, rows: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        if not rows:
            return []
        keys = list(rows[0])
        query = sql.SQL(
            "insert into purchase_request_line ({cols}) values {vals} returning {ret}"
        ).format(
            cols=sql.SQL(", ").join(sql.Identifier(k) for k in keys),
            vals=sql.SQL(", ").join(
                sql.SQL("({})").format(
                    sql.SQL(", ").join(sql.Placeholder(f"{k}_{i}") for k in keys)
                )
                for i in range(len(rows))
            ),
            ret=sql.SQL(LINE_COLUMNS),
        )
        params: dict[str, object] = {}
        for i, r in enumerate(rows):
            for k in keys:
                params[f"{k}_{i}"] = r[k]
        cur.execute(query, params)
        return cur.fetchall()

    def create_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: PurchaseRequestCreate,
        idempotency_key: UUID | None = None,
    ) -> tuple[PurchaseRequest, bool]:
        """Returns `(request, created)`. `created` is `False` on an idempotent replay (a supplied
        `Idempotency-Key` that already exists for this tenant): the caller returns the ORIGINAL
        request with 200, not a new draft with 201. Enforced via `purchase_request`'s own partial
        unique index on `(tenant_id, idempotency_key) where idempotency_key is not null` — the
        same fix `low_stock_report` already had for this exact class of problem, applied here
        because a lost response otherwise let a client retry create a second draft (FR-011).
        """
        client = authenticated_client(self._settings, bearer_token)

        # 0. Idempotent replay BEFORE validation: an existing (tenant, key) request is resolved
        # and replayed without re-running validations (e.g. required_by_date, product existence).
        if idempotency_key is not None:
            replay = self._find_idempotent_replay(
                client=client, member=member, idempotency_key=idempotency_key
            )
            if replay is not None:
                return replay, False

        # 1. Validation BEFORE any write and BEFORE estimate lookup
        self._validate_required_by_date(payload.required_by_date)
        self._validate_request_lines(payload.lines)

        self._authorize_branch_for_write(client, member=member, branch_id=payload.branch_id)
        if payload.cost_centre_id is not None:
            self._validate_cost_centre_branch(
                client, cost_centre_id=payload.cost_centre_id, branch_id=payload.branch_id
            )
        self._validate_products_exist(client, lines=payload.lines)

        # 2. Estimates & Totals
        product_ids = [line.workspace_product_id for line in payload.lines]
        estimates = self._estimate_products(product_ids, member=member)
        quantities = [line.quantity for line in payload.lines]
        total_amount, total_currency, has_incomplete = _compute_totals(quantities, estimates)
        pack_quantities = self._fetch_pack_quantities_batch(
            client, [str(pid) for pid in product_ids]
        )

        request_id = uuid4()
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        lock_id = (
            member.tenant_id.int ^ (idempotency_key.int if idempotency_key else request_id.int)
        ) & 0x7FFFFFFFFFFFFFFF

        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
                    cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))

                    cur.execute(
                        f"""
                        insert into purchase_request (
                            id, tenant_id, branch_id, cost_centre_id,
                            requested_by_membership_id, required_by_date, status,
                            estimated_total_amount, estimated_total_currency,
                            has_incomplete_estimate, idempotency_key
                        ) values (
                            %s, %s, %s, %s, %s,
                            %s, 'draft', %s, %s,
                            %s, %s
                        ) returning {REQUEST_COLUMNS}
                        """,
                        (
                            request_id,
                            member.tenant_id,
                            payload.branch_id,
                            payload.cost_centre_id,
                            member.membership_id,
                            payload.required_by_date.isoformat(),
                            (
                                _format_decimal(total_amount, scale=4)
                                if total_amount is not None
                                else None
                            ),
                            total_currency,
                            has_incomplete,
                            str(idempotency_key) if idempotency_key else None,
                        ),
                    )
                    request_row = cur.fetchone()
                    if request_row is None:
                        raise ServiceUnavailableError(details={"dependency": "database"})

                    line_data = [
                        {
                            "id": uuid4(),
                            "tenant_id": member.tenant_id,
                            "purchase_request_id": request_id,
                            "workspace_product_id": line.workspace_product_id,
                            "position": pos,
                            "quantity": line.quantity,
                            "pack_base_quantity": pack_quantities.get(
                                str(line.workspace_product_id)
                            ),
                            "note": line.note,
                            "estimated_unit_price_amount": (
                                _format_decimal(est.unit_price_amount, scale=4)
                                if est.unit_price_amount is not None
                                else None
                            ),
                            "estimated_unit_price_currency": est.unit_price_currency,
                            "estimated_unit_price_source_landed_cost_id": (
                                est.source_landed_cost_id
                                if est.source_landed_cost_id is not None
                                else None
                            ),
                        }
                        for pos, (line, est) in enumerate(
                            zip(payload.lines, estimates, strict=True)
                        )
                    ]
                    line_rows = self._insert_lines_db(cur, rows=line_data)

        except psycopg.Error as exc:
            if idempotency_key is not None and getattr(exc, "sqlstate", None) == "23505":
                replay = self._find_idempotent_replay(
                    client=client, member=member, idempotency_key=idempotency_key
                )
                if replay is not None:
                    return replay, False
            raise _map_psycopg_error(exc) from exc

        rid = str(request_id)
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_created",
            target={"purchase_request_id": rid},
        )
        return (
            self._purchase_request_with_budget_status(
                client, request_row, line_rows, step_row=None
            ),
            True,
        )

    def _find_idempotent_replay(
        self,
        *,
        client: Client,
        member: CurrentMember,
        idempotency_key: UUID,
    ) -> PurchaseRequest | None:
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
                    cur.execute(
                        f"select {REQUEST_COLUMNS} from purchase_request "
                        "where tenant_id = %s and idempotency_key = %s",
                        (member.tenant_id, str(idempotency_key)),
                    )
                    existing_row = cur.fetchone()
                    if existing_row is None:
                        return None

                    rid = str(existing_row["id"])
                    cur.execute(
                        f"select {LINE_COLUMNS} from purchase_request_line "
                        "where tenant_id = %s and purchase_request_id = %s "
                        "order by position, created_at, id",
                        (member.tenant_id, rid),
                    )
                    existing_lines = cur.fetchall()
                    cur.execute(
                        f"select {STEP_COLUMNS} from approval_step "
                        "where tenant_id = %s and purchase_request_id = %s limit 1",
                        (member.tenant_id, rid),
                    )
                    existing_step = cur.fetchone()
                    return self._purchase_request_with_budget_status(
                        client, existing_row, existing_lines, existing_step
                    )
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _fetch_request_by_idempotency_key(
        self, client: Client, *, idempotency_key: UUID
    ) -> dict[str, object]:
        try:
            response = (
                client.table("purchase_request")
                .select(REQUEST_COLUMNS)
                .eq("idempotency_key", str(idempotency_key))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row(response.data, reason="purchase_request_idempotency_lookup_failed")

    def get_request(
        self,
        *,
        bearer_token: str,
        request_id: UUID,
        member: CurrentMember | None = None,
    ) -> PurchaseRequest:
        if member is not None:
            return self._get_request_for_member(member=member, request_id=request_id)
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)
        rid = str(request_id)
        line_rows = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)
        return self._purchase_request_with_budget_status(client, request_row, line_rows, step_row)

    def validate_approved_request_for_order(
        self,
        *,
        bearer_token: str,
        request_id: UUID,
        member: CurrentMember | None = None,
    ) -> PurchaseRequest:
        if member is not None:
            return self._get_request_for_member(
                member=member, request_id=request_id, require_approval=True
            )
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)
        rid = str(request_id)

        try:
            response = (
                client.table("approval_step")
                .select(STEP_COLUMNS)
                .eq("purchase_request_id", rid)
                .eq("status", "approved")
                .not_.is_("decided_by_membership_id", "null")
                .not_.is_("decided_at", "null")
                .limit(1)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        rows = _rows(response.data)
        if not rows or request_row["status"] not in ORDERABLE_REQUEST_STATUSES:
            raise ConflictError(details={"reason": "request_not_approved"})

        step_row = rows[0]
        line_rows = self._fetch_lines_for(client, rid)
        return self._purchase_request_with_budget_status(client, request_row, line_rows, step_row)

    def _get_request_for_member(
        self,
        *,
        member: CurrentMember,
        request_id: UUID,
        require_approval: bool = False,
        request_group: RequestGroupSummary | None = None,
        request_group_lookup: bool = True,
    ) -> PurchaseRequest:
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        try:
            with db.connect(
                self._settings.database_url.get_secret_value(),
                row_factory=dict_row,
            ) as conn:
                conn.execute("set local role authenticated")
                conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                request_row = conn.execute(
                    f"select {REQUEST_COLUMNS} from purchase_request "
                    "where tenant_id = %s and id = %s",
                    (member.tenant_id, request_id),
                ).fetchone()
                if request_row is None:
                    raise NotFoundError(details={"resource": "purchase_request"})

                step_filter = f" and {approved_step_predicate()}" if require_approval else ""
                step_row = conn.execute(
                    f"select {STEP_COLUMNS} from approval_step "
                    "where tenant_id = %s and purchase_request_id = %s"
                    f"{step_filter} limit 1",
                    (member.tenant_id, request_id),
                ).fetchone()
                if require_approval and (
                    step_row is None or request_row["status"] not in ORDERABLE_REQUEST_STATUSES
                ):
                    raise UnprocessableEntityError(details={"reason": "request_not_approved"})

                line_rows = conn.execute(
                    f"select {LINE_COLUMNS} from purchase_request_line "
                    "where tenant_id = %s and purchase_request_id = %s "
                    "order by position, created_at, id",
                    (member.tenant_id, request_id),
                ).fetchall()

                if request_group_lookup:
                    request_group = self._fetch_request_groups_sql(
                        conn, member=member, request_rows=[request_row]
                    ).get(str(request_id))

                contacts: dict[str, MemberContact] = {}
                try:
                    # A savepoint keeps optional lookup failures from aborting the read.
                    with conn.transaction():
                        contact_ids = [request_row["requested_by_membership_id"]]
                        if step_row:
                            contact_ids.append(step_row["assigned_membership_id"])
                        contacts = {
                            str(row["id"]): _member_contact(row)
                            for row in conn.execute(
                                "select id, email, display_name from membership "
                                "where tenant_id = %s and id = any(%s::uuid[])",
                                (member.tenant_id, contact_ids),
                            ).fetchall()
                        }
                except psycopg.Error:
                    logger.warning("Member contact lookup failed", exc_info=True)

                auto_prepared_row = None
                if request_row.get("source_rfq_response_id"):
                    auto_prepared_row = conn.execute(
                        "select e.guardrail_id, e.rfq_id, e.supplier_id, "
                        "s.name as supplier_name, e.created_at from auto_preparation_event e "
                        "left join supplier s "
                        "on s.tenant_id = e.tenant_id and s.id = e.supplier_id "
                        "where e.tenant_id = %s and e.purchase_request_id = %s "
                        "order by e.created_at limit 1",
                        (member.tenant_id, request_id),
                    ).fetchone()

                source_row = None
                if request_row.get("source_supplier_id"):
                    # The request's own snapshot (20261029060000): RFQ tables are not readable by
                    # approvers or branch managers, the request and supplier tables are.
                    supplier = conn.execute(
                        "select name from supplier where tenant_id = %s and id = %s",
                        (member.tenant_id, request_row["source_supplier_id"]),
                    ).fetchone()
                    source_row = {
                        "rfq_id": request_row["source_rfq_id"],
                        "rfq_response_id": request_row["source_rfq_response_id"],
                        "quotation_id": request_row["source_quotation_id"],
                        "supplier_id": request_row["source_supplier_id"],
                        "supplier_name": supplier["name"] if supplier else None,
                    }
        except (ConflictError, NotFoundError, UnprocessableEntityError):
            raise
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        requester = contacts.get(str(request_row["requested_by_membership_id"]))
        assignee = contacts.get(str(step_row["assigned_membership_id"])) if step_row else None
        return _purchase_request(
            request_row,
            line_rows,
            step_row,
            requester=requester,
            assignee=assignee,
            auto_prepared=(
                AutoPreparedProvenance.model_validate(auto_prepared_row)
                if auto_prepared_row
                else None
            ),
            source=RequestSource.model_validate(source_row) if source_row else None,
            request_group=request_group,
        )

    def list_requests(
        self,
        *,
        bearer_token: str,
        member: CurrentMember | None = None,
        status: PurchaseRequestStatus | None = None,
        branch_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
        eligible_for_order: bool = False,
        sort: PurchaseRequestSort = "created_desc",
        q: str | None = None,
        mine: bool = False,
    ) -> PurchaseRequestList:
        filtered_sql = q is not None or mine or sort != "created_desc"
        if eligible_for_order and not filtered_sql and status is None and branch_id is None:
            if member is None:
                raise UnprocessableEntityError(details={"reason": "member_required"})
            return self.list_requests_eligible_for_order(member=member, cursor=cursor, limit=limit)
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)

        if filtered_sql or eligible_for_order:
            if member is None:
                raise UnprocessableEntityError(details={"reason": "member_required"})
            rows = self._list_request_rows_sql(
                member=member,
                status=status,
                branch_id=branch_id,
                q=q,
                mine=mine,
                sort=sort,
                offset=offset,
                limit=capped + 1,
                eligible_for_order=eligible_for_order,
            )
        else:
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
                raise ServiceUnavailableError(details={"dependency": "database"}) from exc

            rows = _rows(response.data)

        visible = rows[:capped]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None

        if not visible:
            return PurchaseRequestList(items=[], next_cursor=next_cursor)

        if eligible_for_order:
            assert member is not None
            # Reuse the legacy eligible helper's per-row construction, skipping normal
            # list enrichment so filters cannot change item content. Keep the bare path intact.
            return PurchaseRequestList(
                items=[
                    self._get_request_for_member(member=member, request_id=UUID(str(row["id"])))
                    for row in visible
                ],
                next_cursor=next_cursor,
            )

        request_ids = [str(r["id"]) for r in visible]
        lines_by_request = self._fetch_lines_batch(client, request_ids)
        steps_by_request = self._fetch_steps_batch(client, request_ids)
        member_contacts = self._fetch_member_contacts_batch(
            client, visible, list(steps_by_request.values())
        )
        auto_prepared = self._fetch_auto_prepared_batch(client, visible)
        sources = self._fetch_sources_batch(client, visible)
        request_groups = self._fetch_request_groups_batch(client, visible)

        budgets = self._fetch_budget_rows(client)
        spend_cache: dict[UUID, list[SpendRow]] = {}

        def committed_spend(budget: BudgetRow) -> list[SpendRow]:
            if budget.id not in spend_cache:
                spend_cache[budget.id] = self._fetch_committed_spend_rows(client, budget)
            return spend_cache[budget.id]

        def budget_status_for(row: dict[str, object]) -> BudgetStatus | None:
            return _compute_request_budget_status(row, budgets, committed_spend)

        items = []
        for row in visible:
            step = steps_by_request.get(str(row["id"]))
            items.append(
                self._purchase_request_with_budget_status(
                    client,
                    row,
                    lines_by_request.get(str(row["id"]), []),
                    step,
                    requester=member_contacts.get(str(row["requested_by_membership_id"])),
                    assignee=(
                        member_contacts.get(str(step["assigned_membership_id"]))
                        if step is not None
                        else None
                    ),
                    requester_lookup=False,
                    auto_prepared=auto_prepared.get(str(row["id"])),
                    auto_prepared_lookup=False,
                    source=sources.get(str(row["id"])),
                    source_lookup=False,
                    request_group=request_groups.get(str(row["id"])),
                    request_group_lookup=False,
                    budget_status_for=budget_status_for,
                )
            )
        if member is not None:
            from procurepilot_api.modules.orders.service import OrdersService

            orderable = [
                item
                for item in items
                if item.status in ("approved", "ordered")
                and item.approval_step is not None
                and item.approval_step.status == "approved"
            ]
            remaining = OrdersService(self._settings).requests_with_quantity_to_order(
                member=member, request_ids=[item.id for item in orderable]
            )
            for item in orderable:
                item.has_quantity_to_order = item.id in remaining
        return PurchaseRequestList(items=items, next_cursor=next_cursor)

    def _list_request_rows_sql(
        self,
        *,
        member: CurrentMember,
        status: PurchaseRequestStatus | None,
        branch_id: UUID | None,
        q: str | None,
        mine: bool,
        sort: PurchaseRequestSort,
        offset: int,
        limit: int,
        eligible_for_order: bool,
    ) -> list[dict[str, object]]:
        # Run the full filtered page in SQL: no matching-ID cap (including >2000 matches),
        # no oversized PostgREST URL, and only limit+1 rows are materialised.
        predicates = [sql.SQL("true")]
        params: list[object] = []
        for column, value in (
            ("status", status),
            ("branch_id", branch_id),
            ("requested_by_membership_id", member.membership_id if mine else None),
        ):
            if value is not None:
                predicates.append(sql.SQL("pr.{} = %s").format(sql.Identifier(column)))
                params.append(value)
        if q is not None:
            # Escape LIKE syntax before adding our own substring wildcards. Parameters
            # keep both Arabic/Latin text and SQL metacharacters as literal user input.
            pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            predicates.append(
                sql.SQL(
                    "(exists (select 1 from supplier s where s.tenant_id=pr.tenant_id "
                    "and s.id=pr.source_supplier_id and s.name ilike %s) "
                    "or exists (select 1 from purchase_request_line l "
                    "left join workspace_product p on p.tenant_id=l.tenant_id "
                    "and p.id=l.workspace_product_id "
                    "where l.tenant_id=pr.tenant_id and l.purchase_request_id=pr.id "
                    "and (p.tenant_name ilike %s or l.note ilike %s)))"
                )
            )
            params.extend([pattern] * 3)
        if eligible_for_order:
            predicates.append(
                sql.SQL(
                    f"{orderable_request_predicate('pr')} and exists (select 1 "
                    "from approval_step ast where ast.tenant_id=pr.tenant_id "
                    f"and ast.purchase_request_id=pr.id and {approved_step_predicate('ast')}) "
                    "and not exists (select 1 from purchase_order po "
                    "where po.tenant_id=pr.tenant_id and po.source_request_id=pr.id)"
                )
            )
        orders = {
            "created_desc": "pr.created_at desc, pr.id",
            "created_asc": "pr.created_at asc, pr.id",
            "required_by_asc": "pr.required_by_date asc, pr.id",
            "required_by_desc": "pr.required_by_date desc, pr.id",
            # Raw amounts across currencies are ordered numerically; cross-currency
            # totals are not comparable. Unknown totals always follow known totals.
            "total_desc": "pr.estimated_total_amount desc nulls last, pr.id",
            "total_asc": "pr.estimated_total_amount asc nulls last, pr.id",
        }
        # The id tie-break makes a quiet table's offset pages stable. Concurrent inserts
        # can still shift offsets; the web de-duplicates. Retain the existing cursor.
        query = sql.SQL(
            "select pr.* from purchase_request pr where {} order by {} limit %s offset %s"
        ).format(sql.SQL(" and ").join(predicates), sql.SQL(orders[sort]))
        params.extend([limit, offset])
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        try:
            with db.connect(
                self._settings.database_url.get_secret_value(), row_factory=dict_row
            ) as conn:
                # member is resolved from the verified JWT; all joined tables retain RLS.
                conn.execute("set local role authenticated")
                conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                return conn.execute(query, params).fetchall()
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def list_requests_eligible_for_order(
        self, *, member: CurrentMember, cursor: str | None = None, limit: int = 50
    ) -> PurchaseRequestList:
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        try:
            with db.connect(
                self._settings.database_url.get_secret_value(), row_factory=dict_row
            ) as conn:
                conn.execute("set local role authenticated")
                conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                rows = conn.execute(
                    "select pr.id, pr.request_group_id from purchase_request pr "
                    "join approval_step ast "
                    "on ast.tenant_id = pr.tenant_id and ast.purchase_request_id = pr.id "
                    f"where pr.tenant_id = %s and {approved_step_predicate('ast')} "
                    f"and {orderable_request_predicate('pr')} "
                    "and not exists (select 1 from purchase_order po "
                    "where po.tenant_id = pr.tenant_id "
                    "and po.source_request_id = pr.id) order by pr.created_at desc, pr.id "
                    "limit %s offset %s",
                    (member.tenant_id, capped + 1, offset),
                ).fetchall()
                request_groups = self._fetch_request_groups_sql(
                    conn, member=member, request_rows=rows[:capped]
                )
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        visible = rows[:capped]
        items = [
            self._get_request_for_member(
                member=member,
                request_id=UUID(str(row["id"])),
                request_group=request_groups.get(str(row["id"])),
                request_group_lookup=False,
            )
            for row in visible
        ]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None
        return PurchaseRequestList(items=items, next_cursor=next_cursor)

    def list_pending_approvals(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = 50,
        sort: PendingApprovalSort = "submitted_desc",
        branch_id: UUID | None = None,
    ) -> PendingApprovalList:
        boundary = _decode_approval_cursor(cursor, sort=sort, branch_id=branch_id)
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        step_rows, total = self._pending_approval_page(
            member=member, sort=sort, branch_id=branch_id, boundary=boundary, limit=capped
        )
        visible_steps = step_rows[:capped]
        next_cursor = (
            _encode_approval_cursor(
                None
                if visible_steps[-1]["sort_value"] is None
                else str(visible_steps[-1]["sort_value"]),
                UUID(str(visible_steps[-1]["id"])),
                sort=sort,
                branch_id=branch_id,
            )
            if len(step_rows) > capped
            else None
        )
        if not visible_steps:
            return PendingApprovalList(items=[], next_cursor=next_cursor, total=total)

        request_ids = [str(step["purchase_request_id"]) for step in visible_steps]
        request_rows = self._fetch_requests_batch(client, request_ids)
        lines_by_request = self._fetch_lines_batch(client, request_ids)
        member_contacts = self._fetch_member_contacts_batch(client, request_rows, visible_steps)
        auto_prepared = self._fetch_auto_prepared_batch(client, request_rows)
        sources = self._fetch_sources_batch(client, request_rows)
        request_groups = self._fetch_request_groups_batch(client, request_rows)

        items = []
        rows_by_id = {str(row["id"]): row for row in request_rows}
        for step in visible_steps:
            row = rows_by_id.get(str(step["purchase_request_id"]))
            if row is None:
                continue
            items.append(
                self._purchase_request_with_budget_status(
                    client,
                    row,
                    lines_by_request.get(str(row["id"]), []),
                    step,
                    requester=member_contacts.get(str(row["requested_by_membership_id"])),
                    assignee=(
                        member_contacts.get(str(step["assigned_membership_id"]))
                        if step is not None
                        else None
                    ),
                    requester_lookup=False,
                    auto_prepared=auto_prepared.get(str(row["id"])),
                    auto_prepared_lookup=False,
                    source=sources.get(str(row["id"])),
                    source_lookup=False,
                    request_group=request_groups.get(str(row["id"])),
                    request_group_lookup=False,
                )
            )
        return PendingApprovalList(items=items, next_cursor=next_cursor, total=total)

    def _pending_approval_page(
        self,
        *,
        member: CurrentMember,
        sort: PendingApprovalSort,
        branch_id: UUID | None,
        boundary: tuple[str | None, UUID] | None,
        limit: int,
    ) -> tuple[list[dict[str, object]], int]:
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    # Both reads use the verified member's RLS context.
                    cur.execute("set local role authenticated")
                    cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                    cur.execute(
                        "select id from membership where role = 'owner' and status = 'active'"
                    )
                    owners = {UUID(str(row["id"])) for row in cur.fetchall()}
                    options = dict(
                        sort=sort,
                        branch_id=branch_id,
                        membership_id=member.membership_id,
                        is_owner=member.role is MemberRole.owner,
                        is_sole_owner=member.role is MemberRole.owner
                        and owners == {member.membership_id},
                        limit=limit,
                    )
                    query, params = _pending_approval_query(**options, boundary=None, count=True)
                    cur.execute(query, params)
                    total = int(cur.fetchone()["total"])
                    query, params = _pending_approval_query(**options, boundary=boundary)
                    cur.execute(query, params)
                    return cur.fetchall(), total
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def create_low_stock_report(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: LowStockReportCreate,
        idempotency_key: UUID | None,
    ) -> tuple[LowStockReport, bool]:
        """Record a low-stock signal. Insert-only — never touches `purchase_request` (FR-006).

        Returns `(report, created)`. `created` is `False` on an idempotent replay (a supplied
        `Idempotency-Key` that already exists for this tenant): the caller returns the ORIGINAL
        row with 200, not a new one with 201. `low_stock_report`'s own partial unique index on
        `(tenant_id, idempotency_key) where idempotency_key is not null` is what makes this a real
        guarantee rather than a best-effort check — this table's fix for the still-open, separately
        tracked gap where `Idempotency-Key` is accepted but not enforced anywhere else in this
        codebase yet (research.md R4 revised).
        """
        client = authenticated_client(self._settings, bearer_token)
        self._authorize_branch_for_write(client, member=member, branch_id=payload.branch_id)
        row_data = {
            "tenant_id": str(member.tenant_id),
            "branch_id": str(payload.branch_id),
            "member_id": str(member.membership_id),
            "workspace_product_id": str(payload.workspace_product_id),
            "count_remaining": payload.count_remaining,
        }
        if idempotency_key is not None:
            row_data["idempotency_key"] = str(idempotency_key)

        try:
            response = client.table("low_stock_report").insert(row_data).execute()
        except APIError as exc:
            if idempotency_key is not None and _api_error_code(exc) == "23505":
                existing = self._fetch_low_stock_report_by_key(
                    client, idempotency_key=idempotency_key
                )
                return _low_stock_report(existing), False
            raise _write_error(exc) from exc

        row = _one_row(response.data, reason="low_stock_report_write_failed")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.low_stock_report_created",
            target={"low_stock_report_id": str(row["id"])},
        )
        return _low_stock_report(row), True

    def _authorize_branch_for_write(
        self, client: Client, *, member: CurrentMember, branch_id: UUID
    ) -> None:
        """Refuse a low-stock report for a branch outside the caller's own scope.

        `low_stock_report`'s insert RLS only checks `tenant_id` (its migration's own comment:
        "Write authorization ... is an application-layer check, matching this project's standing
        convention rather than a second RLS policy") — without this, any tenant member could POST
        a report against a same-tenant branch they have no assignment to. Mirrors exactly the
        three-way branching `low_stock_report_scoped_visibility`'s own SELECT policy already uses:
        an owner is never scoped; a member with no `branch_role_assignment` row at all is treated
        as unscoped (sees/may act on every branch); a member who HAS at least one assignment must
        have one for this specific branch. `branch` itself has no branch-scoped RLS (every member
        can see every branch in their tenant — it's tenant-wide reference data), so checking
        `branch_role_assignment` directly, not `branch`, is what actually enforces this.
        """
        if member.role is MemberRole.owner:
            return
        try:
            response = (
                client.table("branch_role_assignment")
                .select("branch_id")
                .eq("membership_id", str(member.membership_id))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        assignments = _rows(response.data)
        if not assignments:
            return
        assigned_branch_ids = {str(row["branch_id"]) for row in assignments}
        if str(branch_id) not in assigned_branch_ids:
            # Not a not-found case: branches are tenant-wide visible reference data (branch's own
            # RLS has no scoping), so there's no existence to hide — this is "you may see it, but
            # this isn't a branch you may act on," matching _require_requester's own
            # PermissionDeniedError precedent elsewhere in this file, not the cross-tenant
            # not-found convention.
            raise PermissionDeniedError(details={"reason": "branch_not_assigned"})

    def _fetch_low_stock_report_by_key(
        self, client: Client, *, idempotency_key: UUID
    ) -> dict[str, object]:
        try:
            response = (
                client.table("low_stock_report")
                .select("*")
                .eq("idempotency_key", str(idempotency_key))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row(response.data, reason="low_stock_report_idempotency_lookup_failed")

    def list_low_stock_reports(
        self,
        *,
        bearer_token: str,
        branch_id: UUID | None = None,
        workspace_product_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> LowStockReportList:
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)

        try:
            query = client.table("low_stock_report").select("*")
            if branch_id is not None:
                query = query.eq("branch_id", str(branch_id))
            if workspace_product_id is not None:
                query = query.eq("workspace_product_id", str(workspace_product_id))
            response = (
                query.order("created_at", desc=True)
                .order("id")
                .range(offset, offset + capped)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        rows = _rows(response.data)
        visible = rows[:capped]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None
        items = [_low_stock_report(row) for row in visible]
        return LowStockReportList(items=items, next_cursor=next_cursor)

    def update_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        patch: PurchaseRequestUpdate,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)

        # 1. Validation BEFORE any write
        if "required_by_date" in patch.model_fields_set and patch.required_by_date is not None:
            self._validate_required_by_date(patch.required_by_date)

        if patch.lines is not None:
            self._validate_request_lines(patch.lines)
            self._validate_products_exist(client, lines=patch.lines)

        if "branch_id" in patch.model_fields_set and patch.branch_id is not None:
            self._authorize_branch_for_write(client, member=member, branch_id=patch.branch_id)

        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        lock_id = (member.tenant_id.int ^ request_id.int) & 0x7FFFFFFFFFFFFFFF

        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
                    cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))

                    cur.execute(
                        f"select {REQUEST_COLUMNS} from purchase_request where id = %s for update",
                        (request_id,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise NotFoundError(details={"resource": "purchase_request"})
                    _require_ungrouped(existing)

                    if str(existing["status"]) != "draft":
                        raise ConflictError(details={"reason": "not_draft"})
                    _require_requester(existing, member)

                    effective_branch_id = (
                        patch.branch_id
                        if ("branch_id" in patch.model_fields_set and patch.branch_id is not None)
                        else UUID(str(existing["branch_id"]))
                    )
                    if "cost_centre_id" in patch.model_fields_set:
                        effective_cc_id = patch.cost_centre_id
                    else:
                        effective_cc_id = (
                            UUID(str(existing["cost_centre_id"]))
                            if existing.get("cost_centre_id") is not None
                            else None
                        )

                    if effective_cc_id is not None:
                        self._validate_cost_centre_branch(
                            client,
                            cost_centre_id=effective_cc_id,
                            branch_id=effective_branch_id,
                        )

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
                        estimates = self._estimate_products(
                            product_ids, member=member, request_id=request_id
                        )
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

                        cur.execute(
                            "delete from purchase_request_line where purchase_request_id = %s",
                            (request_id,),
                        )

                        pack_quantities = self._fetch_pack_quantities_batch(
                            client, [str(pid) for pid in product_ids]
                        )
                        line_data = [
                            {
                                "id": uuid4(),
                                "tenant_id": member.tenant_id,
                                "purchase_request_id": request_id,
                                "workspace_product_id": line.workspace_product_id,
                                "position": pos,
                                "quantity": line.quantity,
                                "pack_base_quantity": pack_quantities.get(
                                    str(line.workspace_product_id)
                                ),
                                "note": line.note,
                                "estimated_unit_price_amount": (
                                    _format_decimal(est.unit_price_amount, scale=4)
                                    if est.unit_price_amount is not None
                                    else None
                                ),
                                "estimated_unit_price_currency": est.unit_price_currency,
                                "estimated_unit_price_source_landed_cost_id": (
                                    est.source_landed_cost_id
                                    if est.source_landed_cost_id is not None
                                    else None
                                ),
                            }
                            for pos, (line, est) in enumerate(
                                zip(patch.lines, estimates, strict=True)
                            )
                        ]
                        new_line_rows = self._insert_lines_db(cur, rows=line_data)

                    if updates:
                        set_clauses = [
                            sql.SQL("{} = %s").format(sql.Identifier(k)) for k in updates
                        ]
                        set_clauses.append(sql.SQL("updated_at = now()"))
                        set_stmt = sql.SQL(", ").join(set_clauses)
                        params = list(updates.values())
                        params.append(request_id)
                        cur.execute(
                            sql.SQL(
                                "update purchase_request set {set_stmt} "
                                "where id = %s and status = 'draft' returning {cols}"
                            ).format(set_stmt=set_stmt, cols=sql.SQL(REQUEST_COLUMNS)),
                            params,
                        )
                        request_row = cur.fetchone()
                        if request_row is None:
                            raise ConflictError(details={"reason": "not_draft"})
                    else:
                        request_row = existing

                    rid = str(request_id)
                    if new_line_rows is None:
                        cur.execute(
                            f"select {LINE_COLUMNS} from purchase_request_line "
                            "where purchase_request_id = %s order by position, created_at, id",
                            (request_id,),
                        )
                        new_line_rows = cur.fetchall()

                    cur.execute(
                        f"select {STEP_COLUMNS} from approval_step "
                        "where purchase_request_id = %s limit 1",
                        (request_id,),
                    )
                    step_row = cur.fetchone()

        except psycopg.Error as exc:
            raise _map_psycopg_error(exc) from exc

        rid = str(request_id)
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_updated",
            target={"purchase_request_id": rid},
        )
        return self._purchase_request_with_budget_status(
            client, request_row, new_line_rows, step_row
        )

    def submit_group(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        group_id: UUID,
        idempotency_key: UUID,
    ) -> list[PurchaseRequest]:
        return self._transition_group(
            member=member, group_id=group_id, idempotency_key=idempotency_key, action="submitted"
        )

    def approve_group(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        group_id: UUID,
        idempotency_key: UUID,
        payload: ApprovalDecisionInput,
    ) -> list[PurchaseRequest]:
        return self._transition_group(
            member=member,
            group_id=group_id,
            idempotency_key=idempotency_key,
            action="approved",
            comment=payload.comment,
        )

    def reject_group(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        group_id: UUID,
        idempotency_key: UUID,
        payload: ApprovalDecisionInput,
    ) -> list[PurchaseRequest]:
        return self._transition_group(
            member=member,
            group_id=group_id,
            idempotency_key=idempotency_key,
            action="rejected",
            comment=payload.comment,
        )

    def withdraw_group(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        group_id: UUID,
        idempotency_key: UUID,
    ) -> list[PurchaseRequest]:
        return self._transition_group(
            member=member, group_id=group_id, idempotency_key=idempotency_key, action="withdrawn"
        )

    def _transition_group(
        self,
        *,
        member: CurrentMember,
        group_id: UUID,
        idempotency_key: UUID,
        action: str,
        comment: str | None = None,
    ) -> list[PurchaseRequest]:
        """Serialize the split, then commit requests, steps, audit/replay and outbox together.

        All domain reads/writes use the member's RLS. The service-role windows are limited to
        the private replay journal and notification outbox, after group visibility is checked.
        The append-only audit target holds the response so replay survives later transitions
        without requiring another table or mutating the group's preparation evidence.
        """
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        audit_action = f"requests.group_{action}"
        notification_id = None
        try:
            with db.connect(
                self._settings.database_url.get_secret_value(), row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("set local role authenticated")
                    cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                    cur.execute(
                        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"request-group:{member.tenant_id}:{group_id}",),
                    )
                    cur.execute("select * from purchase_request_group where id=%s", (group_id,))
                    group = cur.fetchone()
                    if group is None:
                        raise NotFoundError(details={"resource": "purchase_request_group"})
                    # Actor-scoped replay cannot disclose a prior decider's response to a
                    # different member. Neither a different key nor action is a replay.
                    cur.execute("set local role service_role")
                    cur.execute(
                        "select target from audit_event where tenant_id=%s and "
                        "actor_membership_id=%s "
                        "and action=%s and outcome='success' and target->>'request_group_id'=%s "
                        "and target->>'idempotency_key'=%s order by id limit 1",
                        (
                            member.tenant_id,
                            member.membership_id,
                            audit_action,
                            str(group_id),
                            str(idempotency_key),
                        ),
                    )
                    replay = cur.fetchone()
                    cur.execute("set local role authenticated")
                    if replay is not None:
                        return _replay_group_response(replay["target"]["response"])

                    cur.execute(
                        "select id from purchase_request where request_group_id=%s order by id",
                        (group_id,),
                    )
                    ids = [row["id"] for row in cur.fetchall()]
                    # Same locks/order as single withdrawal and PO creation: advisory locks
                    # precede row locks, so a PO cannot slip past the live-order check.
                    cur.execute(
                        "select pg_advisory_xact_lock(lock_id) from unnest(%s::bigint[]) as "
                        "locks(lock_id)",
                        ([(member.tenant_id.int ^ id_.int) & 0x7FFFFFFFFFFFFFFF for id_ in ids],),
                    )
                    cur.execute(
                        f"select {REQUEST_COLUMNS} from purchase_request where request_group_id=%s "
                        "order by id for update",
                        (group_id,),
                    )
                    rows = cur.fetchall()
                    statuses = {str(row["status"]) for row in rows}
                    expected = "draft" if action == "submitted" else "submitted"
                    if action != "withdrawn" and statuses != {expected}:
                        raise ConflictError(details={"reason": f"not_{expected}"})
                    if action == "withdrawn" and (
                        not statuses
                        or not (
                            statuses <= {"approved", "ordered"}
                            or statuses in ({"draft"}, {"submitted"})
                        )
                    ):
                        raise ConflictError(details={"reason": "already_decided_or_withdrawn"})
                    if (
                        not rows
                        or any(row["branch_id"] != group["branch_id"] for row in rows)
                        or len({row["requested_by_membership_id"] for row in rows}) != 1
                    ):
                        raise ConflictError(details={"reason": "invalid_group"})
                    if action in ("submitted", "withdrawn"):
                        for row in rows:
                            if action == "submitted" or member.role is not MemberRole.owner:
                                _require_requester(row, member)
                    if action in ("approved", "rejected"):
                        _validate_decision_comment(action, comment)
                    now = _now_iso()
                    if action == "submitted":
                        total = sum(
                            (
                                Decimal(str(row["estimated_total_amount"]))
                                for row in rows
                                if row["estimated_total_amount"] is not None
                            ),
                            Decimal("0"),
                        )
                        if (
                            any(
                                row["estimated_total_amount"] is None
                                or row["estimated_total_currency"]
                                != group["combined_total_currency"]
                                or row["has_incomplete_estimate"]
                                for row in rows
                            )
                            or total != group["combined_total_amount"]
                        ):
                            raise ConflictError(details={"reason": "invalid_group"})
                        cur.execute("select * from threshold_rule")
                        rules = [_threshold_rule_row(row) for row in cur.fetchall()]
                        as_of = datetime.now(UTC).date()
                        cur.execute(
                            "select * from approval_delegation where starts_on<=%s and ends_on>=%s",
                            (as_of, as_of),
                        )
                        delegations = [_delegation_row(row) for row in cur.fetchall()]
                        cur.execute("select id,role,status from membership")
                        members = cur.fetchall()
                        owner = next(
                            (
                                row["id"]
                                for row in members
                                if row["role"] == "owner" and row["status"] == "active"
                            ),
                            None,
                        )
                        if owner is None:
                            raise ConflictError(details={"reason": "owner_membership_not_found"})
                        resolved = resolve_approver(
                            request_value=total,
                            request_currency=str(group["combined_total_currency"]),
                            branch_id=group["branch_id"],
                            rules=rules,
                            delegations=delegations,
                            removed_membership_ids={
                                row["id"] for row in members if row["status"] != "active"
                            },
                            owner_membership_id=owner,
                            owner_membership_ids=[
                                row["id"]
                                for row in members
                                if row["role"] == "owner" and row["status"] == "active"
                            ],
                            requester_membership_id=rows[0]["requested_by_membership_id"],
                            as_of=as_of,
                            is_group=True,
                        )
                        cur.execute(
                            "update purchase_request set status='submitted', submitted_at=%s, "
                            "updated_at=%s "
                            "where id=any(%s::uuid[]) returning *",
                            (now, now, ids),
                        )
                        rows = cur.fetchall()
                        cur.execute(
                            "insert into approval_step "
                            "(tenant_id,purchase_request_id,assigned_membership_id,source,status) "
                            "select %s, id, %s, %s::approval_step_source, 'pending' from "
                            "unnest(%s::uuid[]) as requests(id) returning *",
                            (
                                member.tenant_id,
                                resolved.assigned_membership_id,
                                resolved.source,
                                ids,
                            ),
                        )
                        steps = cur.fetchall()
                        if resolved.source == "owner_fallback":
                            for step in steps:
                                cur.execute(
                                    "select record_audit_event(%s,'success',%s,%s,%s,%s,%s)",
                                    (
                                        "requests.approval_step_escalated",
                                        member.tenant_id,
                                        member.membership_id,
                                        member.email,
                                        Jsonb(
                                            {
                                                "purchase_request_id": str(
                                                    step["purchase_request_id"]
                                                ),
                                                "approval_step_id": str(step["id"]),
                                                "assigned_membership_id": str(
                                                    step["assigned_membership_id"]
                                                ),
                                            }
                                        ),
                                        get_trace_id(),
                                    ),
                                )
                    else:
                        cur.execute(
                            "select * from approval_step where "
                            "purchase_request_id=any(%s::uuid[]) order by id for update",
                            (ids,),
                        )
                        steps = cur.fetchall()
                        if action in ("approved", "rejected"):
                            if len(steps) != len(rows):
                                if member.role is not MemberRole.owner:
                                    raise PermissionDeniedError(
                                        details={"reason": "not_assigned_approver"}
                                    )
                                raise ConflictError(details={"reason": "not_submitted"})
                            if any(step["status"] != "pending" for step in steps):
                                raise ConflictError(details={"reason": "not_submitted"})
                            for step in steps:
                                _require_assigned_approver_or_owner(step, member)
                            if len({step["assigned_membership_id"] for step in steps}) != 1:
                                raise ConflictError(details={"reason": "invalid_group"})
                            step_by_request = {
                                str(step["purchase_request_id"]): step for step in steps
                            }
                            decided = [
                                self._apply_request_decision(
                                    cur,
                                    member=member,
                                    request_id=str(row["id"]),
                                    step_id=str(step_by_request[str(row["id"])]["id"]),
                                    decision=action,
                                    request_status=action,
                                    comment=comment,
                                    now=now,
                                )
                                for row in rows
                            ]
                            rows = [request for request, _ in decided]
                            steps = [step for _, step in decided]
                        else:
                            if statuses & {"approved", "ordered"}:
                                cur.execute(
                                    "select 1 from purchase_order where "
                                    "source_request_id=any(%s::uuid[]) and status<>'cancelled' "
                                    "limit 1",
                                    (ids,),
                                )
                                if cur.fetchone() is not None:
                                    raise ConflictError(details={"reason": "purchase_order_exists"})
                            cur.execute(
                                "update purchase_request set "
                                "status='withdrawn',withdrawn_at=%s,updated_at=%s "
                                "where id=any(%s::uuid[]) returning *",
                                (now, now, ids),
                            )
                            rows = cur.fetchall()
                    result = self._group_response(
                        conn, member=member, group=group, rows=rows, steps=steps
                    )
                    target = {
                        "request_group_id": str(group_id),
                        "purchase_request_ids": [str(id_) for id_ in ids],
                        "approval_step_ids": [str(step["id"]) for step in steps],
                        "actor_membership_id": str(member.membership_id),
                        "comment": comment,
                        "idempotency_key": str(idempotency_key),
                        "response": [item.model_dump(mode="json") for item in result],
                    }
                    if action in ("approved", "rejected") and str(
                        rows[0]["requested_by_membership_id"]
                    ) == str(member.membership_id):
                        target["self_approved"] = True
                    cur.execute(
                        "select record_audit_event(%s,'success',%s,%s,%s,%s,%s)",
                        (
                            audit_action,
                            member.tenant_id,
                            member.membership_id,
                            member.email,
                            Jsonb(target),
                            get_trace_id(),
                        ),
                    )
                    if action in ("approved", "rejected"):
                        cur.execute("set local role service_role")
                        cur.execute(
                            "insert into push_notification "
                            "(tenant_id,purchase_request_id,member_id) values (%s,%s,%s) "
                            "returning id",
                            (member.tenant_id, result[0].id, rows[0]["requested_by_membership_id"]),
                        )
                        notification_id = cur.fetchone()["id"]
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if notification_id is not None:
            try:
                enqueue_push_job(self._settings, notification_id)
            except Exception:
                logger.exception(
                    "push notification enqueue failed after a committed group decision",
                    extra={
                        "request_group_id": str(group_id),
                        "notification_id": str(notification_id),
                    },
                )
        return result

    def _group_response(
        self,
        conn: psycopg.Connection,
        *,
        member: CurrentMember,
        group: dict[str, object],
        rows: list[dict[str, object]],
        steps: list[dict[str, object]],
    ) -> list[PurchaseRequest]:
        """Build and freeze the response within the mutation transaction, under member RLS.

        Lines, contacts, provenance and budgets are batched; spend is loaded once per selected
        budget, scoped to its currency/period. This also sees the group's just-written statuses.
        """
        rows = sorted(rows, key=lambda row: (row["created_at"], row["id"]))
        ids = [row["id"] for row in rows]
        lines = conn.execute(
            f"select {LINE_COLUMNS} from purchase_request_line "
            "where purchase_request_id=any(%s::uuid[]) order by position,created_at,id",
            (ids,),
        ).fetchall()
        contacts = conn.execute(
            "select pr.id, m.email as requester_email, m.display_name as requester_name, "
            "a.email as assigned_email, a.display_name as assigned_name, s.name as "
            "supplier_name, "
            "row_to_json(e) as auto_prepared from purchase_request pr "
            "left join membership m on m.id=pr.requested_by_membership_id and "
            "m.tenant_id=pr.tenant_id "
            "left join approval_step ast on ast.purchase_request_id=pr.id and "
            "ast.tenant_id=pr.tenant_id "
            "left join membership a on a.id=ast.assigned_membership_id and "
            "a.tenant_id=pr.tenant_id "
            "left join supplier s on s.id=pr.source_supplier_id and s.tenant_id=pr.tenant_id "
            "left join auto_preparation_event e on e.purchase_request_id=pr.id and "
            "e.tenant_id=pr.tenant_id "
            "where pr.id=any(%s::uuid[])",
            (ids,),
        ).fetchall()
        contacts_by_id = {str(row["id"]): row for row in contacts}
        budgets = [
            _budget_row(row)
            for row in conn.execute(f"select {BUDGET_COLUMNS} from budget").fetchall()
        ]
        spend_cache: dict[UUID, list[SpendRow]] = {}

        def spend(budget: BudgetRow) -> list[SpendRow]:
            if budget.id not in spend_cache:
                spend_rows = conn.execute(
                    "select * from purchase_request where "
                    "status=any(%s::purchase_request_status[]) "
                    "and estimated_total_currency=%s and required_by_date>=%s and "
                    "required_by_date<%s "
                    "and (%s::uuid is null or branch_id=%s) and (%s::uuid is null or "
                    "cost_centre_id=%s)",
                    (
                        list(COMMITTED_SPEND_STATUSES),
                        budget.currency,
                        budget.period_start,
                        budget_period_end(budget),
                        budget.branch_id,
                        budget.branch_id,
                        budget.cost_centre_id,
                        budget.cost_centre_id,
                    ),
                ).fetchall()
                spend_cache[budget.id] = [
                    _spend_row(row)
                    for row in spend_rows
                    if row["estimated_total_amount"] is not None
                ]
            return spend_cache[budget.id]

        summaries = _request_group_summaries(
            [
                {
                    **row,
                    "request_group": group,
                    "supplier_name": contacts_by_id[str(row["id"])]["supplier_name"],
                }
                for row in rows
            ]
        )
        steps_by_request = {str(step["purchase_request_id"]): step for step in steps}
        result = []
        for row in rows:
            rid = str(row["id"])
            contact = contacts_by_id[rid]
            request_lines = [line for line in lines if line["purchase_request_id"] == row["id"]]
            source = (
                RequestSource(
                    rfq_id=row["source_rfq_id"],
                    rfq_response_id=row["source_rfq_response_id"],
                    quotation_id=row["source_quotation_id"],
                    supplier_id=row["source_supplier_id"],
                    supplier_name=contact["supplier_name"],
                )
                if row.get("source_supplier_id")
                else None
            )
            auto = contact["auto_prepared"]
            if auto:
                auto = {**auto, "supplier_name": contact["supplier_name"]}
            result.append(
                _purchase_request(
                    row,
                    request_lines,
                    steps_by_request.get(rid),
                    request_group=summaries[rid],
                    requester=MemberContact(contact["requester_email"], contact["requester_name"]),
                    assignee=MemberContact(contact["assigned_email"], contact["assigned_name"]),
                    source=source,
                    auto_prepared=AutoPreparedProvenance.model_validate(auto) if auto else None,
                    quoted_prices=self._quoted_prices_for(row, request_lines),
                    budget_status=compute_budget_status(
                        request_id=row["id"],
                        request_amount=row["estimated_total_amount"],
                        request_currency=row["estimated_total_currency"],
                        branch_id=row["branch_id"],
                        cost_centre_id=row["cost_centre_id"],
                        required_by=row["required_by_date"],
                        budgets=budgets,
                        committed_spend=spend,
                    ),
                )
            )
        return result

    def submit_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        idempotency_key: UUID | None = None,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        lock_id = (member.tenant_id.int ^ request_id.int) & 0x7FFFFFFFFFFFFFFF

        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
                    cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))

                    cur.execute(
                        f"select {REQUEST_COLUMNS} from purchase_request where id = %s for update",
                        (request_id,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise NotFoundError(details={"resource": "purchase_request"})
                    _require_ungrouped(existing)
                    _require_requester(existing, member)

                    is_replay = False
                    if idempotency_key is not None:
                        cur.execute("set local role service_role")
                        cur.execute(
                            "select 1 from audit_event where tenant_id = %s "
                            "and actor_membership_id = %s "
                            "and action = %s and outcome = 'success' "
                            "and target->>'purchase_request_id' = %s "
                            "and target->>'idempotency_key' = %s order by id limit 1",
                            (
                                member.tenant_id,
                                member.membership_id,
                                "requests.purchase_request_submitted",
                                str(request_id),
                                str(idempotency_key),
                            ),
                        )
                        replay = cur.fetchone()
                        cur.execute("set local role authenticated")
                        if replay is not None:
                            is_replay = True

                    if is_replay:
                        cur.execute(
                            f"select {LINE_COLUMNS} from purchase_request_line "
                            "where purchase_request_id = %s order by position, created_at, id",
                            (request_id,),
                        )
                        frozen_lines = cur.fetchall()
                        cur.execute(
                            f"select {STEP_COLUMNS} from approval_step "
                            "where purchase_request_id = %s order by created_at desc limit 1",
                            (request_id,),
                        )
                        routed_step = cur.fetchone()
                        request_row = existing
                        resolved = None
                    else:
                        if str(existing["status"]) != "draft":
                            raise ConflictError(details={"reason": "not_draft"})

                        rid = str(request_id)
                        cur.execute(
                            f"select {LINE_COLUMNS} from purchase_request_line "
                            "where purchase_request_id = %s order by position, created_at, id",
                            (request_id,),
                        )
                        line_rows = cur.fetchall()
                        if not line_rows:
                            raise UnprocessableEntityError(details={"reason": "no_lines"})

                        product_ids = [UUID(str(lr["workspace_product_id"])) for lr in line_rows]
                        estimates = self._estimate_products(
                            product_ids, member=member, request_id=request_id
                        )

                        now = _now_iso()
                        for lr, est in zip(line_rows, estimates, strict=True):
                            cur.execute(
                                """
                                update purchase_request_line set
                                    estimated_unit_price_amount = %s,
                                    estimated_unit_price_currency = %s,
                                    estimated_unit_price_source_landed_cost_id = %s,
                                    estimated_at = %s
                                where id = %s
                                """,
                                (
                                    _format_decimal(est.unit_price_amount, scale=4)
                                    if est.unit_price_amount is not None
                                    else None,
                                    est.unit_price_currency,
                                    (
                                        str(est.source_landed_cost_id)
                                        if est.source_landed_cost_id is not None
                                        else None
                                    ),
                                    now,
                                    lr["id"],
                                ),
                            )

                        quantities = [_decimal(lr["quantity"], scale=6) for lr in line_rows]
                        total_amount, total_currency, has_incomplete = _compute_totals(
                            quantities, estimates
                        )

                        cur.execute(
                            f"""
                            update purchase_request set
                                status = 'submitted',
                                submitted_at = %s,
                                estimated_total_amount = %s,
                                estimated_total_currency = %s,
                                has_incomplete_estimate = %s,
                                updated_at = %s
                            where id = %s and status = 'draft'
                            returning {REQUEST_COLUMNS}
                            """,
                            (
                                now,
                                (
                                    _format_decimal(total_amount, scale=4)
                                    if total_amount is not None
                                    else None
                                ),
                                total_currency,
                                has_incomplete,
                                now,
                                request_id,
                            ),
                        )
                        request_row = cur.fetchone()
                        if request_row is None:
                            raise ConflictError(details={"reason": "not_draft"})

                        as_of = datetime.now(UTC).date()
                        resolved = resolve_approver(
                            request_value=(
                                Decimal(str(request_row["estimated_total_amount"]))
                                if request_row.get("estimated_total_amount") is not None
                                else None
                            ),
                            request_currency=(
                                str(request_row["estimated_total_currency"])
                                if request_row.get("estimated_total_currency") is not None
                                else None
                            ),
                            branch_id=UUID(str(request_row["branch_id"])),
                            rules=self._fetch_threshold_rules(client),
                            delegations=self._fetch_active_delegations(client, as_of=as_of),
                            removed_membership_ids=self._fetch_removed_membership_ids(client),
                            owner_membership_id=self._fetch_owner_membership_id(client),
                            owner_membership_ids=self._fetch_owner_membership_ids(client),
                            requester_membership_id=UUID(
                                str(request_row["requested_by_membership_id"])
                            ),
                            as_of=as_of,
                        )

                        cur.execute(
                            f"""
                            insert into approval_step (
                                id, tenant_id, purchase_request_id,
                                assigned_membership_id, source, status
                            ) values (
                                %s, %s, %s, %s, %s, 'pending'
                            ) returning {STEP_COLUMNS}
                            """,
                            (
                                uuid4(),
                                member.tenant_id,
                                request_id,
                                resolved.assigned_membership_id,
                                resolved.source,
                            ),
                        )
                        routed_step = cur.fetchone()

                        cur.execute(
                            f"select {LINE_COLUMNS} from purchase_request_line "
                            "where purchase_request_id = %s order by position, created_at, id",
                            (request_id,),
                        )
                        frozen_lines = cur.fetchall()

                        audit_target: dict[str, object] = {"purchase_request_id": rid}
                        if idempotency_key is not None:
                            audit_target["idempotency_key"] = str(idempotency_key)
                        self._record(
                            cur=cur,
                            bearer_token=bearer_token,
                            member=member,
                            action="requests.purchase_request_submitted",
                            target=audit_target,
                        )

                        if resolved is not None and resolved.source == "owner_fallback":
                            escalation_target: dict[str, object] = {
                                "purchase_request_id": rid,
                                "approval_step_id": str(routed_step["id"]),
                                "assigned_membership_id": str(resolved.assigned_membership_id),
                            }
                            if idempotency_key is not None:
                                escalation_target["idempotency_key"] = str(idempotency_key)
                            self._record(
                                cur=cur,
                                bearer_token=bearer_token,
                                member=member,
                                action="requests.approval_step_escalated",
                                target=escalation_target,
                            )

        except psycopg.Error as exc:
            raise _map_psycopg_error(exc) from exc

        return self._purchase_request_with_budget_status(
            client, request_row, frozen_lines, routed_step
        )

    def withdraw_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        idempotency_key: UUID | None = None,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        rid = str(request_id)
        request_row, previous_status, is_replay = self._withdraw_request_row(
            member, request_id, idempotency_key=idempotency_key
        )
        line_rows = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)
        return self._purchase_request_with_budget_status(client, request_row, line_rows, step_row)

    def _withdraw_request_row(
        self,
        member: CurrentMember,
        request_id: UUID,
        idempotency_key: UUID | None = None,
    ) -> tuple[dict[str, object], str | None, bool]:
        # Use the same transaction lock as PO creation/editing so the absence check
        # and withdrawal cannot interleave with attaching a live purchase order.
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )
                    lock_id = (member.tenant_id.int ^ request_id.int) & 0x7FFFFFFFFFFFFFFF
                    cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))
                    cur.execute(
                        f"select {REQUEST_COLUMNS} from purchase_request where id = %s for update",
                        (request_id,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise NotFoundError(details={"resource": "purchase_request"})
                    _require_ungrouped(existing)
                    if member.role is not MemberRole.owner:
                        _require_requester(existing, member)

                    is_replay = False
                    if idempotency_key is not None:
                        cur.execute("set local role service_role")
                        cur.execute(
                            "select 1 from audit_event where tenant_id = %s "
                            "and actor_membership_id = %s "
                            "and action = %s and outcome = 'success' "
                            "and target->>'purchase_request_id' = %s "
                            "and target->>'idempotency_key' = %s order by id limit 1",
                            (
                                member.tenant_id,
                                member.membership_id,
                                "requests.purchase_request_withdrawn",
                                str(request_id),
                                str(idempotency_key),
                            ),
                        )
                        replay = cur.fetchone()
                        cur.execute("set local role authenticated")
                        if replay is not None:
                            is_replay = True

                    if is_replay:
                        return existing, None, True

                    previous_status = str(existing["status"])
                    if previous_status not in ("draft", "submitted", "approved", "ordered"):
                        raise ConflictError(details={"reason": "already_decided_or_withdrawn"})
                    if previous_status in ("approved", "ordered"):
                        cur.execute(
                            "select 1 from purchase_order where source_request_id = %s "
                            "and status <> 'cancelled' limit 1",
                            (request_id,),
                        )
                        if cur.fetchone() is not None:
                            raise ConflictError(details={"reason": "purchase_order_exists"})
                    cur.execute(
                        "update purchase_request set status = 'withdrawn', "
                        "withdrawn_at = now(), updated_at = now() where id = %s "
                        f"returning {REQUEST_COLUMNS}",
                        (request_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError(details={"resource": "purchase_request"})

                    audit_target: dict[str, object] = {
                        "purchase_request_id": str(request_id),
                        "previous_status": previous_status,
                    }
                    if idempotency_key is not None:
                        audit_target["idempotency_key"] = str(idempotency_key)
                    self._record(
                        cur=cur,
                        member=member,
                        action="requests.purchase_request_withdrawn",
                        target=audit_target,
                    )
                    return row, previous_status, False
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def confirm_delivery(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: DeliveryConfirmationCreate,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._fetch_request(client, request_id)

        if str(existing["status"]) != "ordered":
            raise ConflictError(details={"reason": "not_ordered"})
        # No branch-write check here on purpose: `_fetch_request` above already went through
        # `purchase_request_scoped_visibility`'s restrictive RLS policy, which is a strict
        # superset of a branch-assignment check (same `branch_role_assignment` row, same
        # owner/unscoped/assigned-branch shape) — a branch mismatch has already failed as a 404
        # by this point, so re-checking it here could only ever be unreachable. The requester
        # confirming their own delivery, or an owner/unscoped/correctly-assigned member doing so
        # for someone else, are both already the only ways to have reached this line at all.

        rid = str(request_id)
        line_rows = self._fetch_lines_for(client, rid)
        line_rows_by_id = {str(row["id"]): row for row in line_rows}
        received_by_line_id: dict[str, Decimal] = {}
        for line in payload.lines:
            line_id = str(line.purchase_request_line_id)
            if line_id in received_by_line_id:
                raise UnprocessableEntityError(details={"reason": "duplicate_line"})
            if line_id not in line_rows_by_id:
                # Reject instead of ignoring: the payload must describe this request's lines only.
                raise UnprocessableEntityError(details={"reason": "line_not_in_request"})
            received_by_line_id[line_id] = Decimal(line.quantity_received)

        has_discrepancy = False
        for row in line_rows:
            received = received_by_line_id.get(str(row["id"]))
            if received is None:
                # An omitted line has no confirmed received quantity, so treat it as short.
                has_discrepancy = True
                continue
            if received < Decimal(str(row["quantity"])):
                has_discrepancy = True

        for line_id, received in received_by_line_id.items():
            try:
                client.table("purchase_request_line").update(
                    {"quantity_received": _format_decimal(received, scale=6)}
                ).eq("id", line_id).execute()
            except APIError as exc:
                raise _write_error(exc) from exc

        now = _now_iso()
        try:
            response = (
                client.table("purchase_request")
                .update(
                    {
                        "status": "delivered",
                        "delivered_at": now,
                        "delivery_confirmed_by_membership_id": str(member.membership_id),
                        "has_delivery_discrepancy": has_discrepancy,
                        "updated_at": now,
                    }
                )
                .eq("id", rid)
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc

        request_row = _one_row_or_not_found(response.data, resource="purchase_request")
        confirmed_lines = self._fetch_lines_for(client, rid)
        step_row = self._fetch_step(client, rid)

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.delivery_confirmed",
            target={"purchase_request_id": rid},
        )
        return self._purchase_request_with_budget_status(
            client, request_row, confirmed_lines, step_row
        )

    def create_quality_issue(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: QualityIssueCreate,
    ) -> QualityIssue:
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)

        if str(request_row["status"]) != "delivered":
            raise ConflictError(details={"reason": "not_delivered"})

        try:
            response = (
                client.table("delivery_quality_issue")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "purchase_request_id": str(request_id),
                        "reported_by_membership_id": str(member.membership_id),
                        "description": payload.description,
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc

        row = _one_row(response.data, reason="quality_issue_write_failed")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.quality_issue_reported",
            target={"delivery_quality_issue_id": str(row["id"])},
        )
        return _quality_issue(row, photos=[])

    def list_quality_issues(
        self,
        *,
        bearer_token: str,
        request_id: UUID,
    ) -> QualityIssueList:
        client = authenticated_client(self._settings, bearer_token)
        self._fetch_request(client, request_id)
        try:
            response = (
                client.table("delivery_quality_issue")
                .select(QUALITY_ISSUE_COLUMNS)
                .eq("purchase_request_id", str(request_id))
                .order("created_at", desc=True)
                .order("id")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        rows = _rows(response.data)
        photos_by_issue = self._fetch_quality_issue_photos_batch(
            client, [str(row["id"]) for row in rows]
        )
        items = [
            _quality_issue(row, photos=photos_by_issue.get(str(row["id"]), [])) for row in rows
        ]
        return QualityIssueList(items=items)

    def attach_quality_issue_photo(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        issue_id: UUID,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> QualityIssuePhoto:
        client = authenticated_client(self._settings, bearer_token)
        issue_row = self._fetch_quality_issue(client, issue_id)
        tenant_id = UUID(str(issue_row["tenant_id"]))
        storage_path = _quality_issue_storage_path(
            tenant_id=tenant_id,
            issue_id=issue_id,
            filename=filename,
        )
        bucket = self._settings.quality_issue_photos_bucket

        try:
            file_options: dict[str, str] = {"upsert": "false"}
            if content_type:
                file_options["content-type"] = content_type
            client.storage.from_(bucket).upload(
                storage_path,
                content,
                file_options=file_options,
            )
        except TypeError:
            try:
                client.storage.from_(bucket).upload(
                    storage_path,
                    content,
                    {"content-type": content_type} if content_type else None,
                )
            except Exception as exc:
                raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc

        try:
            response = (
                client.table("delivery_quality_issue_photo")
                .insert(
                    {
                        "tenant_id": str(tenant_id),
                        "delivery_quality_issue_id": str(issue_id),
                        "storage_path": storage_path,
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row(response.data, reason="quality_issue_photo_write_failed")

        url = self._create_quality_issue_photo_url(client, storage_path)
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.quality_issue_photo_attached",
            target={"delivery_quality_issue_photo_id": str(row["id"])},
        )
        return _quality_issue_photo(row, url=url)

    def approve_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: ApprovalDecisionInput,
        idempotency_key: UUID | None = None,
    ) -> PurchaseRequest:
        return self._decide_request(
            bearer_token=bearer_token,
            member=member,
            request_id=request_id,
            payload=payload,
            idempotency_key=idempotency_key,
            decision="approved",
        )

    def reject_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: ApprovalDecisionInput,
        idempotency_key: UUID | None = None,
    ) -> PurchaseRequest:
        return self._decide_request(
            bearer_token=bearer_token,
            member=member,
            request_id=request_id,
            payload=payload,
            idempotency_key=idempotency_key,
            decision="rejected",
        )

    def list_threshold_rules(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ThresholdRuleList:
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)
        try:
            response = (
                client.table("threshold_rule")
                .select(THRESHOLD_RULE_COLUMNS)
                .order("branch_id")
                .order("min_amount")
                .order("id")
                .range(offset, offset + capped)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        return ThresholdRuleList(
            items=[_threshold_rule(row) for row in rows[:capped]],
            next_cursor=(_encode_cursor(offset + capped) if len(rows) > capped else None),
        )

    def create_threshold_rule(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: ThresholdRuleCreate,
    ) -> ThresholdRule:
        _require_owner(member)
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("threshold_rule")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "branch_id": (
                            str(payload.branch_id) if payload.branch_id is not None else None
                        ),
                        "min_amount": payload.min_amount,
                        "max_amount": payload.max_amount,
                        "currency": payload.currency,
                        "approver_membership_id": str(payload.approver_membership_id),
                        "created_by": str(member.membership_id),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row(response.data, reason="threshold_rule_write_failed")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.threshold_rule_created",
            target={"threshold_rule_id": str(row["id"])},
        )
        return _threshold_rule(row)

    def update_threshold_rule(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        rule_id: UUID,
        patch: ThresholdRuleUpdate,
    ) -> ThresholdRule:
        _require_owner(member)
        updates: dict[str, object] = {}
        for field in (
            "branch_id",
            "min_amount",
            "max_amount",
            "currency",
            "approver_membership_id",
        ):
            if field not in patch.model_fields_set:
                continue
            value = getattr(patch, field)
            updates[field] = str(value) if isinstance(value, UUID) else value
        updates["updated_at"] = _now_iso()

        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("threshold_rule").update(updates).eq("id", str(rule_id)).execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row_or_not_found(response.data, resource="threshold_rule")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.threshold_rule_updated",
            target={"threshold_rule_id": str(rule_id)},
        )
        return _threshold_rule(row)

    def delete_threshold_rule(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        rule_id: UUID,
    ) -> None:
        _require_owner(member)
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.table("threshold_rule").delete().eq("id", str(rule_id)).execute()
        except APIError as exc:
            raise _write_error(exc) from exc
        _one_row_or_not_found(response.data, resource="threshold_rule")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.threshold_rule_deleted",
            target={"threshold_rule_id": str(rule_id)},
        )

    def list_approval_delegations(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        membership_id: UUID | None = None,
    ) -> ApprovalDelegationList:
        if membership_id is not None and member.role is not MemberRole.owner:
            if str(membership_id) != str(member.membership_id):
                raise PermissionDeniedError(details={"reason": "not_delegator_or_owner"})
        client = authenticated_client(self._settings, bearer_token)
        delegator_id = membership_id or member.membership_id
        try:
            response = (
                client.table("approval_delegation")
                .select(DELEGATION_COLUMNS)
                .eq("delegator_membership_id", str(delegator_id))
                .order("starts_on", desc=True)
                .order("id")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return ApprovalDelegationList(
            items=[_approval_delegation(row) for row in _rows(response.data)]
        )

    def create_approval_delegation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: ApprovalDelegationCreate,
    ) -> ApprovalDelegation:
        delegator_id = payload.delegator_membership_id or member.membership_id
        if member.role is not MemberRole.owner and str(delegator_id) != str(member.membership_id):
            raise PermissionDeniedError(details={"reason": "not_delegator_or_owner"})

        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("approval_delegation")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "delegator_membership_id": str(delegator_id),
                        "delegate_membership_id": str(payload.delegate_membership_id),
                        "starts_on": payload.starts_on.isoformat(),
                        "ends_on": payload.ends_on.isoformat(),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row(response.data, reason="approval_delegation_write_failed")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.approval_delegation_created",
            target={"approval_delegation_id": str(row["id"])},
        )
        return _approval_delegation(row)

    def cancel_approval_delegation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        delegation_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._fetch_delegation(client, delegation_id)
        if member.role is not MemberRole.owner and str(existing["delegator_membership_id"]) != str(
            member.membership_id
        ):
            raise PermissionDeniedError(details={"reason": "not_delegator_or_owner"})
        try:
            response = (
                client.table("approval_delegation").delete().eq("id", str(delegation_id)).execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        _one_row_or_not_found(response.data, resource="approval_delegation")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.approval_delegation_cancelled",
            target={"approval_delegation_id": str(delegation_id)},
        )

    # ── internal helpers ──────────────────────────────────────────────

    def _estimate_products(
        self, product_ids: list[UUID], *, member: CurrentMember, request_id: UUID | None = None
    ) -> list[LineEstimate]:
        """Per-pack estimates. A request prepared from an RFQ response is valued at that
        response's quoted prices; any product not on it (or any other request) falls back to
        the latest landed cost per pack.

        Read inside the caller's own database role and claims, so a product, request or quote
        of another workspace has no estimate (PPS-185)."""
        db_url = self._settings.database_url.get_secret_value()
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        with db.connect(db_url) as conn:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
            source_quotation_id = None
            if request_id is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        "select source_quotation_id from purchase_request where id = %s",
                        (request_id,),
                    )
                    row = cur.fetchone()
                if row is not None:
                    source_quotation_id = row[0]
            sourced: dict[UUID, LineEstimate] = {}
            if source_quotation_id is not None:
                # The request's own snapshot of the quotation it was prepared from, read through
                # the quotation tables, not the RFQ tables a requester may no longer read.
                sourced = estimate_from_source_quotation(
                    conn, quotation_id=source_quotation_id, product_ids=product_ids
                )
            return [
                sourced[pid]
                if pid in sourced
                else estimate_line_value(conn, workspace_product_id=pid)
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
        product_ids = list(dict.fromkeys(str(line.workspace_product_id) for line in payload_lines))
        pack_quantities = self._fetch_pack_quantities_batch(client, product_ids)
        inserts = [
            {
                "tenant_id": tenant_id,
                "purchase_request_id": request_id,
                "workspace_product_id": str(line.workspace_product_id),
                "position": position,
                "quantity": line.quantity,
                "pack_base_quantity": pack_quantities.get(str(line.workspace_product_id)),
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
            for position, (line, est) in enumerate(zip(payload_lines, estimates, strict=True))
        ]
        try:
            response = client.table("purchase_request_line").insert(inserts).execute()
        except APIError as exc:
            raise _write_error(exc) from exc
        return _rows(response.data)

    def _fetch_pack_quantities_batch(
        self, client: Client, product_ids: list[str]
    ) -> dict[str, object]:
        if not product_ids:
            return {}
        try:
            response = (
                client.table("pack_definition")
                .select("workspace_product_id,base_quantity")
                .in_("workspace_product_id", product_ids)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        # RLS scopes this lookup to the verified tenant. Match the migration's newest-wins rule.
        result: dict[str, object] = {}
        for row in _rows(response.data):
            result.setdefault(str(row["workspace_product_id"]), row["base_quantity"])
        return result

    def _fetch_request(self, client: Client, request_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("purchase_request")
                .select(REQUEST_COLUMNS)
                .eq("id", str(request_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="purchase_request")

    def _fetch_quality_issue(self, client: Client, issue_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("delivery_quality_issue")
                .select(QUALITY_ISSUE_COLUMNS)
                .eq("id", str(issue_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="delivery_quality_issue")

    def _fetch_quality_issue_photos_batch(
        self, client: Client, issue_ids: list[str]
    ) -> dict[str, list[QualityIssuePhoto]]:
        if not issue_ids:
            return {}
        try:
            response = (
                client.table("delivery_quality_issue_photo")
                .select(QUALITY_ISSUE_PHOTO_COLUMNS)
                .in_("delivery_quality_issue_id", issue_ids)
                .order("created_at")
                .order("id")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        result: dict[str, list[QualityIssuePhoto]] = {issue_id: [] for issue_id in issue_ids}
        for row in _rows(response.data):
            issue_id = str(row["delivery_quality_issue_id"])
            if issue_id not in result:
                continue
            result[issue_id].append(
                _quality_issue_photo(
                    row,
                    url=self._create_quality_issue_photo_url(client, str(row["storage_path"])),
                )
            )
        return result

    def _fetch_requests_batch(
        self, client: Client, request_ids: list[str]
    ) -> list[dict[str, object]]:
        if not request_ids:
            return []
        try:
            response = (
                client.table("purchase_request")
                .select(REQUEST_COLUMNS)
                .in_("id", request_ids)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows_by_id = {str(row["id"]): row for row in _rows(response.data)}
        return [rows_by_id[request_id] for request_id in request_ids if request_id in rows_by_id]

    def _fetch_product_details_batch(
        self, client: Client, product_ids: list[str]
    ) -> dict[str, dict[str, object | None]]:
        if not product_ids:
            return {}
        try:
            response = (
                client.table("workspace_product")
                .select("id,tenant_name,canonical_product(base_unit)")
                .in_("id", product_ids)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        result: dict[str, dict[str, object | None]] = {}
        for row in _rows(response.data):
            p_id = str(row["id"])
            product_name = str(row["tenant_name"]) if row.get("tenant_name") is not None else None

            base_unit: str | None = None
            if isinstance(row.get("canonical_product"), dict):
                cu = row["canonical_product"].get("base_unit")
                base_unit = str(cu) if cu is not None else None
            elif isinstance(row.get("canonical_product"), list) and row["canonical_product"]:
                cu = row["canonical_product"][0].get("base_unit")
                base_unit = str(cu) if cu is not None else None

            result[p_id] = {
                "product_name": product_name,
                "base_unit": base_unit,
            }
        return result

    def _fetch_lines_for(self, client: Client, request_id: str) -> list[dict[str, object]]:
        return self._fetch_lines_batch(client, [request_id]).get(request_id, [])

    def _fetch_lines_batch(
        self, client: Client, request_ids: list[str]
    ) -> dict[str, list[dict[str, object]]]:
        if not request_ids:
            return {}
        line_rows: list[dict[str, object]] = []
        page_size = 1000
        try:
            while True:
                offset = len(line_rows)
                response = (
                    client.table("purchase_request_line")
                    .select(LINE_COLUMNS)
                    .in_("purchase_request_id", request_ids)
                    .order("position")
                    .order("created_at")
                    .order("id")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                page = _rows(response.data)
                line_rows.extend(page)
                if len(page) < page_size:
                    break
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        product_ids = list(
            {str(r["workspace_product_id"]) for r in line_rows if r.get("workspace_product_id")}
        )
        product_details = self._fetch_product_details_batch(client, product_ids)

        result: dict[str, list[dict[str, object]]] = {rid: [] for rid in request_ids}
        for row in line_rows:
            p_info = product_details.get(str(row.get("workspace_product_id")), {})
            row["product_name"] = p_info.get("product_name")
            row["base_unit"] = p_info.get("base_unit")

            rid = str(row["purchase_request_id"])
            if rid in result:
                result[rid].append(row)
        return result

    def _fetch_step(self, client: Client, request_id: str) -> dict[str, object] | None:
        try:
            response = (
                client.table("approval_step")
                .select(STEP_COLUMNS)
                .eq("purchase_request_id", request_id)
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        return rows[0] if rows else None

    def _fetch_threshold_rules(self, client: Client) -> list[ThresholdRuleRow]:
        try:
            response = client.table("threshold_rule").select(THRESHOLD_RULE_COLUMNS).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return [_threshold_rule_row(row) for row in _rows(response.data)]

    def _fetch_active_delegations(self, client: Client, *, as_of: date) -> list[DelegationRow]:
        try:
            response = (
                client.table("approval_delegation")
                .select(DELEGATION_COLUMNS)
                .lte("starts_on", as_of.isoformat())
                .gte("ends_on", as_of.isoformat())
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return [_delegation_row(row) for row in _rows(response.data)]

    def _fetch_owner_membership_id(self, client: Client) -> UUID:
        try:
            response = (
                client.table("membership")
                .select("id")
                .eq("role", "owner")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        row = _one_row(response.data, reason="owner_membership_not_found")
        return UUID(str(row["id"]))

    def _fetch_owner_membership_ids(self, client: Client) -> list[UUID]:
        owners: list[UUID] = []
        page_size = 1000
        try:
            while True:
                offset = len(owners)
                response = (
                    client.table("membership")
                    .select("id")
                    .eq("role", "owner")
                    .eq("status", "active")
                    .order("id")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                page = _rows(response.data)
                owners.extend(UUID(str(row["id"])) for row in page)
                if len(page) < page_size:
                    return owners
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _fetch_removed_membership_ids(self, client: Client) -> set[UUID]:
        try:
            response = client.table("membership").select("id").neq("status", "active").execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return {UUID(str(row["id"])) for row in _rows(response.data)}

    def _fetch_budget_rows(self, client: Client) -> list[BudgetRow]:
        try:
            response = client.table("budget").select(BUDGET_COLUMNS).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return [_budget_row(row) for row in _rows(response.data)]

    def _fetch_committed_spend_rows(self, client: Client, budget: BudgetRow) -> list[SpendRow]:
        """Committed requests that draw on ``budget``: its currency, period and scope.

        Ordered and delivered requests accumulate forever, and PostgREST caps a response at
        the Data API row limit, so filter in the query and page through the result.
        """
        spend_rows = []
        offset = 0
        while True:
            query = (
                client.table("purchase_request")
                .select(
                    "id,branch_id,cost_centre_id,required_by_date,"
                    "estimated_total_amount,estimated_total_currency,status"
                )
                .in_("status", list(COMMITTED_SPEND_STATUSES))
                .eq("estimated_total_currency", budget.currency)
                .gte("required_by_date", budget.period_start.isoformat())
                .lt("required_by_date", budget_period_end(budget).isoformat())
            )
            if budget.scope == "branch" and budget.branch_id is not None:
                query = query.eq("branch_id", str(budget.branch_id))
            elif budget.scope == "cost_centre" and budget.cost_centre_id is not None:
                query = query.eq("cost_centre_id", str(budget.cost_centre_id))
            try:
                response = (
                    query.order("id")
                    .range(offset, offset + COMMITTED_SPEND_PAGE_SIZE - 1)
                    .execute()
                )
            except APIError as exc:
                raise ServiceUnavailableError(details={"dependency": "database"}) from exc
            page = _rows(response.data)
            for row in page:
                if (
                    row.get("estimated_total_amount") is None
                    or row.get("estimated_total_currency") is None
                ):
                    continue
                spend_rows.append(_spend_row(row))
            if len(page) < COMMITTED_SPEND_PAGE_SIZE:
                return spend_rows
            offset += COMMITTED_SPEND_PAGE_SIZE

    def _fetch_delegation(self, client: Client, delegation_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("approval_delegation")
                .select(DELEGATION_COLUMNS)
                .eq("id", str(delegation_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="approval_delegation")

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
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        result: dict[str, dict[str, object] | None] = {rid: None for rid in request_ids}
        for row in _rows(response.data):
            rid = str(row["purchase_request_id"])
            if rid in result:
                result[rid] = row
        return result

    def _record(
        self,
        *,
        bearer_token: str | None = None,
        member: CurrentMember,
        action: str,
        target: dict[str, object],
        cur: psycopg.Cursor | None = None,
    ) -> None:
        if cur is not None:
            cur.execute(
                "select record_audit_event(%s,'success',%s,%s,%s,%s,%s)",
                (
                    action,
                    member.tenant_id,
                    member.membership_id,
                    member.email,
                    Jsonb(target),
                    get_trace_id(),
                ),
            )
            return
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

    def _create_submission_approval_step(
        self,
        client: Client,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_row: dict[str, object],
    ) -> dict[str, object]:
        as_of = datetime.now(UTC).date()
        resolved = resolve_approver(
            request_value=(
                Decimal(str(request_row["estimated_total_amount"]))
                if request_row.get("estimated_total_amount") is not None
                else None
            ),
            request_currency=(
                str(request_row["estimated_total_currency"])
                if request_row.get("estimated_total_currency") is not None
                else None
            ),
            branch_id=UUID(str(request_row["branch_id"])),
            rules=self._fetch_threshold_rules(client),
            delegations=self._fetch_active_delegations(client, as_of=as_of),
            removed_membership_ids=self._fetch_removed_membership_ids(client),
            owner_membership_id=self._fetch_owner_membership_id(client),
            owner_membership_ids=self._fetch_owner_membership_ids(client),
            requester_membership_id=UUID(str(request_row["requested_by_membership_id"])),
            as_of=as_of,
        )
        try:
            response = (
                client.table("approval_step")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "purchase_request_id": str(request_row["id"]),
                        "assigned_membership_id": str(resolved.assigned_membership_id),
                        "source": resolved.source,
                        "status": "pending",
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row(response.data, reason="approval_step_write_failed")
        if resolved.source == "owner_fallback":
            self._record(
                bearer_token=bearer_token,
                member=member,
                action="requests.approval_step_escalated",
                target={
                    "purchase_request_id": str(request_row["id"]),
                    "approval_step_id": str(row["id"]),
                    "assigned_membership_id": str(resolved.assigned_membership_id),
                },
            )
        return row

    def escalate_pending_steps_for_removed_member(
        self,
        *,
        bearer_token: str,
        actor: CurrentMember,
        removed_membership_id: UUID,
    ) -> int:
        """FR-009: a member removed from the workspace with requests still pending their decision
        must not strand those requests. Reassign every still-pending approval_step assigned to
        them to the owner (source ``owner_fallback``) — the same escalation routing already
        applies at submission time to a branch with no approver.

        Called from the member-removal flow (members/service.py) AFTER the membership row is
        marked ``removed``, so ``_fetch_owner_membership_id`` already excludes the just-removed
        member (which matters when a co-owner is the one being removed). Returns the number of
        steps escalated; each one is audited (FR-013), mirroring the submission-time escalation.

        Only ``pending`` steps are touched — a decided step is history and the request has
        already moved on. The per-row update repeats the ``status = 'pending'`` guard so a
        decision landing concurrently is skipped rather than overwritten.
        """
        client = authenticated_client(self._settings, bearer_token)
        try:
            query = (
                client.table("approval_step")
                .select("id,purchase_request_id,purchase_request!inner(status)")
                .eq("assigned_membership_id", str(removed_membership_id))
                .eq("status", "pending")
            )
            for status in TERMINAL_REQUEST_STATUSES:
                query = query.neq("purchase_request.status", status)
            pending_response = query.execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        pending_rows = _rows(pending_response.data)
        if not pending_rows:
            return 0

        owner_membership_id = self._fetch_owner_membership_id(client)
        escalated = 0
        for row in pending_rows:
            try:
                update_response = (
                    client.table("approval_step")
                    .update(
                        {
                            "assigned_membership_id": str(owner_membership_id),
                            "source": "owner_fallback",
                        }
                    )
                    .eq("id", str(row["id"]))
                    .eq("status", "pending")
                    .execute()
                )
            except APIError as exc:
                raise _write_error(exc) from exc
            if not _rows(update_response.data):
                continue
            escalated += 1
            self._record(
                bearer_token=bearer_token,
                member=actor,
                action="requests.approval_step_escalated",
                target={
                    "purchase_request_id": str(row["purchase_request_id"]),
                    "approval_step_id": str(row["id"]),
                    "assigned_membership_id": str(owner_membership_id),
                    "reason": "assigned_approver_removed",
                },
            )
        return escalated

    def _decide_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: ApprovalDecisionInput,
        decision: str,
        idempotency_key: UUID | None = None,
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)
        _require_ungrouped(request_row)
        rid = str(request_id)
        step_row = None
        if idempotency_key is None:
            if str(request_row["status"]) != "submitted":
                raise ConflictError(details={"reason": "not_submitted"})
            step_row = self._fetch_step(client, rid)
            if step_row is None or str(step_row["status"]) != "pending":
                raise ConflictError(details={"reason": "no_pending_approval"})
            _require_assigned_approver_or_owner(step_row, member)
            _validate_decision_comment(decision, payload.comment)
        now = _now_iso()
        decided_request, decided_step, notification_id = self._decide_and_notify(
            member=member,
            request_id=rid,
            step_id=str(step_row["id"]) if step_row else None,
            decision=decision,
            comment=payload.comment,
            now=now,
            idempotency_key=idempotency_key,
        )

        if notification_id is not None:
            try:
                enqueue_push_job(self._settings, notification_id)
            except Exception:
                # The push_notification row already committed durably above — a lost enqueue
                # does not lose the decision or the outbox record, only its (currently manual;
                # no scheduler exists yet in this codebase to auto-retry it) delivery attempt.
                logger.exception(
                    "push notification enqueue failed after a committed decision",
                    extra={
                        "purchase_request_id": rid,
                        "notification_id": str(notification_id),
                    },
                )

        line_rows = self._fetch_lines_for(client, rid)
        return self._purchase_request_with_budget_status(
            client, decided_request, line_rows, decided_step
        )

    def _apply_request_decision(
        self,
        cur: psycopg.Cursor,
        *,
        member: CurrentMember,
        request_id: str,
        step_id: str,
        decision: str,
        request_status: str,
        comment: str | None,
        now: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Shared guarded writes; the caller owns the transaction and outbox."""
        cur.execute("select * from purchase_request where id=%s for update", (request_id,))
        request_row = cur.fetchone()
        if request_row is None or str(request_row["status"]) != "submitted":
            raise ConflictError(details={"reason": "not_submitted"})
        cur.execute("select * from approval_step where id=%s for update", (step_id,))
        step_row = cur.fetchone()
        # Preserve the guarded-write conflict for a stale unkeyed authorization pre-check.
        if (
            step_row is None
            or str(step_row["status"]) != "pending"
            or (
                member.role is not MemberRole.owner
                and str(step_row["assigned_membership_id"]) != str(member.membership_id)
            )
        ):
            raise ConflictError(details={"reason": "no_pending_approval"})
        _require_self_decision_allowed(cur, request_row, member)
        cur.execute(
            """
            update purchase_request
            set status = %s, updated_at = %s
            where id = %s and status = 'submitted'
            returning *
            """,
            (request_status, now, request_id),
        )
        decided_request = cur.fetchone()
        if decided_request is None:
            raise ConflictError(details={"reason": "not_submitted"})

        # Repeats the assigned-approver-or-owner check the pre-check already made
        # (`_require_assigned_approver_or_owner`, run before this transaction opened)
        # directly in the WHERE clause — approval_step's own RLS is read-only on
        # authorization (its migration: "Write authorization ... is an application-layer
        # RBAC check"), so without this the pre-check's result could go stale between the
        # read and this write. Concretely: the step gets reassigned/escalated (e.g. the
        # approver is removed from the workspace mid-decision, via
        # escalate_pending_steps_for_removed_member) after the pre-check passed but before
        # this statement runs — without re-checking here, the now-unassigned former
        # approver's decision would still apply (review finding).
        is_owner = member.role is MemberRole.owner
        cur.execute(
            """
            update approval_step
            set status = %s, comment = %s, decided_by_membership_id = %s, decided_at = %s
            where id = %s
              and status = 'pending'
              and (%s or assigned_membership_id = %s)
            returning *
            """,
            (
                decision,
                comment,
                str(member.membership_id),
                now,
                step_id,
                is_owner,
                str(member.membership_id),
            ),
        )
        decided_step = cur.fetchone()
        if decided_step is None:
            raise ConflictError(details={"reason": "no_pending_approval"})

        return dict(decided_request), dict(decided_step)

    def _decide_and_notify(
        self,
        *,
        member: CurrentMember,
        request_id: str,
        step_id: str | None,
        decision: str,
        comment: str | None,
        now: str,
        idempotency_key: UUID | None = None,
    ) -> tuple[dict[str, object], dict[str, object], UUID | None]:
        """Atomically applies a decision, records its audit event and queues its notification.

        A single raw-`psycopg` transaction (mirroring `devices/service.py`'s own
        `_authenticated_db`-style pattern — a deliberate, isolated exception to this file's
        otherwise-uniform PostgREST/`authenticated_client` style) because `push_notification`
        grants nothing to `authenticated` at all (its own migration: service-role only), so the
        notification write needs a role switch mid-transaction that PostgREST/supabase-py cannot
        express, and because these writes must succeed or fail together — a prior version of
        this method did them as separate PostgREST calls with no such guarantee (fixed after
        review caught it). Returns `(decided_request, decided_step, notification_id)` — the last
        is `None` for a replay, which has no new notification to enqueue, or defensively
        for a request with no requester to notify.
        """
        claims = {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("set local role authenticated")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),),
                    )

                    if idempotency_key is not None:
                        lock_id = (member.tenant_id.int ^ UUID(request_id).int) & 0x7FFFFFFFFFFFFFFF
                        cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))
                        cur.execute(
                            f"select {REQUEST_COLUMNS} from purchase_request "
                            "where id = %s for update",
                            (request_id,),
                        )
                        existing = cur.fetchone()
                        if existing is None:
                            raise NotFoundError(details={"resource": "purchase_request"})
                        _require_ungrouped(existing)
                        cur.execute(
                            f"select {STEP_COLUMNS} from approval_step "
                            "where purchase_request_id = %s "
                            "order by created_at desc limit 1 for update",
                            (request_id,),
                        )
                        current_step = cur.fetchone()
                        if current_step is None:
                            raise ConflictError(details={"reason": "no_pending_approval"})
                        _require_assigned_approver_or_owner(current_step, member)
                        cur.execute("set local role service_role")
                        cur.execute(
                            "select 1 from audit_event where tenant_id = %s "
                            "and actor_membership_id = %s "
                            "and action = %s and outcome = 'success' "
                            "and target->>'purchase_request_id' = %s "
                            "and target->>'idempotency_key' = %s order by id limit 1",
                            (
                                member.tenant_id,
                                member.membership_id,
                                f"requests.approval_step_{decision}",
                                request_id,
                                str(idempotency_key),
                            ),
                        )
                        replay = cur.fetchone()
                        cur.execute("set local role authenticated")
                        if replay is not None:
                            return dict(existing), dict(current_step), None
                        if str(existing["status"]) != "submitted":
                            raise ConflictError(details={"reason": "not_submitted"})
                        if str(current_step["status"]) != "pending":
                            raise ConflictError(details={"reason": "no_pending_approval"})
                        _validate_decision_comment(decision, comment)
                        step_id = str(current_step["id"])

                    # Same authoritative guard the previous (non-atomic) version used: if a
                    # concurrent withdrawal already flipped the request's status, this matches zero
                    # rows and we raise before touching the step or writing a notification, leaving
                    # the step `pending` rather than stranding a `decided` step on a non-submitted
                    # request.
                    # Approval remains approved until a live purchase order exists (ADR-025).
                    decided_request, decided_step = self._apply_request_decision(
                        cur,
                        member=member,
                        request_id=request_id,
                        step_id=step_id,
                        decision=decision,
                        request_status=decision,
                        comment=comment,
                        now=now,
                    )

                    target = {
                        "purchase_request_id": request_id,
                        "approval_step_id": str(decided_step["id"]),
                        "decided_by_membership_id": str(member.membership_id),
                    }
                    if str(decided_request["requested_by_membership_id"]) == str(
                        member.membership_id
                    ):
                        target["self_approved"] = True
                    if idempotency_key is not None:
                        target["idempotency_key"] = str(idempotency_key)
                    if comment is not None:
                        target["comment"] = comment
                    cur.execute(
                        "select record_audit_event(%s,'success',%s,%s,%s,%s,%s)",
                        (
                            f"requests.approval_step_{decision}",
                            member.tenant_id,
                            member.membership_id,
                            member.email,
                            Jsonb(target),
                            get_trace_id(),
                        ),
                    )

                    cur.execute("set local role service_role")
                    cur.execute(
                        """
                        insert into push_notification (tenant_id, purchase_request_id, member_id)
                        values (%s, %s, %s)
                        returning id
                        """,
                        (
                            str(member.tenant_id),
                            request_id,
                            str(decided_request["requested_by_membership_id"]),
                        ),
                    )
                    notification_row = cur.fetchone()
                    notification_id = (
                        UUID(str(notification_row["id"])) if notification_row is not None else None
                    )
                # Exiting the `with db.connect(...)` block here commits all writes above
                # atomically (or rolls all of them back if any exception was raised) — psycopg's
                # own connection context manager semantics, the same ones `devices/service.py`
                # relies on.
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return dict(decided_request), dict(decided_step), notification_id

    def _purchase_request_with_budget_status(
        self,
        client: Client,
        request_row: dict[str, object],
        line_rows: list[dict[str, object]],
        step_row: dict[str, object] | None,
        *,
        requester: MemberContact | None = None,
        assignee: MemberContact | None = None,
        requester_lookup: bool = True,
        auto_prepared: AutoPreparedProvenance | None = None,
        auto_prepared_lookup: bool = True,
        source: RequestSource | None = None,
        source_lookup: bool = True,
        request_group: RequestGroupSummary | None = None,
        request_group_lookup: bool = True,
        budget_status_for: Callable[[dict[str, object]], BudgetStatus | None] | None = None,
    ) -> PurchaseRequest:
        if requester_lookup:
            member_contacts = self._fetch_member_contacts_batch(
                client, [request_row], [step_row] if step_row else []
            )
            requester = member_contacts.get(str(request_row["requested_by_membership_id"]))
            assignee = (
                member_contacts.get(str(step_row["assigned_membership_id"])) if step_row else None
            )
        if auto_prepared_lookup:
            auto_prepared = self._fetch_auto_prepared_batch(client, [request_row]).get(
                str(request_row["id"])
            )
        if source_lookup:
            source = self._fetch_sources_batch(client, [request_row]).get(str(request_row["id"]))
        if request_group_lookup:
            request_group = self._fetch_request_groups_batch(client, [request_row]).get(
                str(request_row["id"])
            )
        return _purchase_request(
            request_row,
            line_rows,
            step_row,
            budget_status=(
                budget_status_for(request_row)
                if budget_status_for is not None
                else self._budget_status_for(client, request_row)
            ),
            quoted_prices=self._quoted_prices_for(request_row, line_rows),
            requester=requester,
            assignee=assignee,
            auto_prepared=auto_prepared,
            source=source,
            request_group=request_group,
        )

    def _fetch_request_groups_batch(
        self, client: Client, request_rows: list[dict[str, object]]
    ) -> dict[str, RequestGroupSummary]:
        """One RLS read of every visible sibling, including those outside the current page.

        Embed the group through the composite FK, so an invisible group is null. Start
        from requests so branch RLS also controls the count, position and sibling links.
        """
        group_ids = sorted(
            {str(r["request_group_id"]) for r in request_rows if r.get("request_group_id")}
        )
        if not group_ids:
            return {}
        tenant_ids = sorted({str(r["tenant_id"]) for r in request_rows})
        try:
            rows = _rows(
                client.table("purchase_request")
                .select(
                    "id,request_group_id,created_at,source_rfq_id,source_rfq_response_id,"
                    "source_quotation_id,source_supplier_id,"
                    "request_group:purchase_request_group!purchase_request_request_group_fkey("
                    f"id,{GROUP_TOTAL_COLUMNS})"
                )
                .in_("tenant_id", tenant_ids)
                .in_("request_group_id", group_ids)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        sources = self._fetch_sources_batch(client, rows)
        return _request_group_summaries(
            [
                {
                    **row,
                    "supplier_name": sources[str(row["id"])].supplier_name
                    if str(row["id"]) in sources
                    else None,
                }
                for row in rows
            ]
        )

    def _fetch_request_groups_sql(
        self,
        conn: psycopg.Connection,
        *,
        member: CurrentMember,
        request_rows: list[dict[str, object]],
    ) -> dict[str, RequestGroupSummary]:
        """Same batch as PostgREST, on the existing authenticated SQL transaction."""
        group_ids = sorted(
            {str(r["request_group_id"]) for r in request_rows if r.get("request_group_id")}
        )
        if not group_ids:
            return {}
        columns = ", ".join(f"g.{c}" for c in GROUP_TOTAL_COLUMNS.split(","))
        rows = conn.execute(
            f"select pr.id, pr.request_group_id, pr.created_at, s.name as supplier_name, {columns} "
            "from purchase_request pr join purchase_request_group g "
            "on g.tenant_id = pr.tenant_id and g.id = pr.request_group_id "
            "left join supplier s on s.tenant_id = pr.tenant_id and s.id = pr.source_supplier_id "
            "where pr.tenant_id = %s and pr.request_group_id = any(%s::uuid[])",
            (member.tenant_id, group_ids),
        ).fetchall()
        return _request_group_summaries(
            [
                {
                    **row,
                    "request_group": {
                        "id": row["request_group_id"],
                        **{c: row[c] for c in GROUP_TOTAL_COLUMNS.split(",")},
                    },
                }
                for row in rows
            ]
        )

    def _fetch_sources_batch(
        self, client: Client, request_rows: list[dict[str, object]]
    ) -> dict[str, RequestSource]:
        """RFQ, quotation and supplier per request prepared from an RFQ response (R1-H4).

        Built from the request's own source snapshot (20261029060000) so approvers and branch
        managers, who cannot read the RFQ tables, still see the supplier.
        """
        sourced = [row for row in request_rows if row.get("source_supplier_id")]
        if not sourced:
            return {}
        supplier_ids = sorted({str(row["source_supplier_id"]) for row in sourced})
        try:
            suppliers = _rows(
                client.table("supplier").select("id,name").in_("id", supplier_ids).execute().data
            )
        except APIError:
            logger.warning("Request source supplier lookup failed", exc_info=True)
            suppliers = []
        supplier_names = {str(s["id"]): s.get("name") for s in suppliers}
        return {
            str(row["id"]): RequestSource(
                rfq_id=row["source_rfq_id"],
                rfq_response_id=row["source_rfq_response_id"],
                quotation_id=row["source_quotation_id"],
                supplier_id=row["source_supplier_id"],
                supplier_name=supplier_names.get(str(row["source_supplier_id"])),
            )
            for row in sourced
        }

    def _fetch_auto_prepared_batch(
        self, client: Client, request_rows: list[dict[str, object]]
    ) -> dict[str, AutoPreparedProvenance]:
        """Guardrail provenance per request id (finding 38a). Only a request prepared from an RFQ
        response can have one, so others cost no query. auto_preparation_event is readable by
        anyone who can read the request it prepared (20261018000008)."""
        request_ids = [str(row["id"]) for row in request_rows if row.get("source_rfq_response_id")]
        if not request_ids:
            return {}
        try:
            events = _rows(
                client.table("auto_preparation_event")
                .select("purchase_request_id,guardrail_id,rfq_id,supplier_id,created_at")
                .in_("purchase_request_id", request_ids)
                .execute()
                .data
            )
            supplier_ids = sorted({str(e["supplier_id"]) for e in events if e.get("supplier_id")})
            supplier_names: dict[str, str] = {}
            if supplier_ids:
                suppliers = _rows(
                    client.table("supplier")
                    .select("id,name")
                    .in_("id", supplier_ids)
                    .execute()
                    .data
                )
                supplier_names = {str(row["id"]): str(row["name"]) for row in suppliers}
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        provenance: dict[str, AutoPreparedProvenance] = {}
        for event in sorted(events, key=lambda e: str(e["created_at"])):
            request_id = str(event["purchase_request_id"])
            if request_id in provenance:
                continue
            supplier_id = str(event["supplier_id"]) if event.get("supplier_id") else None
            provenance[request_id] = AutoPreparedProvenance(
                guardrail_id=UUID(str(event["guardrail_id"])),
                rfq_id=UUID(str(event["rfq_id"])) if event.get("rfq_id") else None,
                supplier_id=UUID(supplier_id) if supplier_id else None,
                supplier_name=supplier_names.get(supplier_id) if supplier_id else None,
                created_at=event["created_at"],
            )
        return provenance

    def _fetch_member_contacts_batch(
        self,
        client: Client,
        request_rows: list[dict[str, object]],
        step_rows: list[dict[str, object] | None],
    ) -> dict[str, MemberContact]:
        membership_ids = {str(row["requested_by_membership_id"]) for row in request_rows}
        membership_ids.update(
            str(row["assigned_membership_id"]) for row in step_rows if row is not None
        )
        if not membership_ids:
            return {}
        try:
            response = (
                client.table("membership")
                .select("id,email,display_name")
                .in_("id", list(membership_ids))
                .execute()
            )
            return {str(row["id"]): _member_contact(row) for row in _rows(response.data)}
        except Exception:
            logger.warning("Membership email lookup failed", exc_info=True)
            return {}

    def _quoted_prices_for(
        self, request_row: dict[str, object], line_rows: list[dict[str, object]]
    ) -> dict[UUID, QuotedPrice]:
        """Quoted per-pack prices of an RFQ-sourced request's source response, by product."""
        source = request_row.get("source_rfq_response_id")
        if not source or not line_rows:
            return {}
        product_ids = [UUID(str(lr["workspace_product_id"])) for lr in line_rows]
        try:
            with db.connect(self._settings.database_url.get_secret_value()) as conn:
                return quoted_prices_from_source_response(
                    conn, rfq_response_id=UUID(str(source)), product_ids=product_ids
                )
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _budget_status_for(
        self,
        client: Client,
        request_row: dict[str, object],
    ) -> BudgetStatus | None:
        return _compute_request_budget_status(
            request_row,
            self._fetch_budget_rows(client),
            lambda budget: self._fetch_committed_spend_rows(client, budget),
        )

    def _create_quality_issue_photo_url(self, client: Client, storage_path: str) -> str:
        try:
            result = client.storage.from_(
                self._settings.quality_issue_photos_bucket
            ).create_signed_url(storage_path, expires_in=300)
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        return _signed_url(result)


def _compute_request_budget_status(
    request_row: dict[str, object],
    budgets: list[BudgetRow],
    committed_spend: Callable[[BudgetRow], list[SpendRow]],
) -> BudgetStatus | None:
    return compute_budget_status(
        request_id=UUID(str(request_row["id"])),
        request_amount=(
            Decimal(str(request_row["estimated_total_amount"]))
            if request_row.get("estimated_total_amount") is not None
            else None
        ),
        request_currency=(
            str(request_row["estimated_total_currency"])
            if request_row.get("estimated_total_currency") is not None
            else None
        ),
        branch_id=UUID(str(request_row["branch_id"])),
        cost_centre_id=(
            UUID(str(request_row["cost_centre_id"])) if request_row.get("cost_centre_id") else None
        ),
        required_by=_parse_date(request_row["required_by_date"]),
        budgets=budgets,
        committed_spend=committed_spend,
    )


def get_requests_service() -> RequestsService:
    return RequestsService()


# ── module-level helpers ──────────────────────────────────────────────


def _require_ungrouped(request_row: dict[str, object]) -> None:
    if request_row.get("request_group_id"):
        raise ConflictError(
            details={
                "reason": "part_of_split",
                "request_group_id": str(request_row["request_group_id"]),
            }
        )


def _require_requester(request_row: dict[str, object], member: CurrentMember) -> None:
    if str(request_row["requested_by_membership_id"]) != str(member.membership_id):
        raise PermissionDeniedError(details={"reason": "not_requester"})


def _require_self_decision_allowed(
    cur: psycopg.Cursor, request_row: dict[str, object], member: CurrentMember
) -> None:
    """Check current active owners inside the decision transaction (ADR-024)."""
    if str(request_row["requested_by_membership_id"]) != str(member.membership_id):
        return
    cur.execute("select id from membership where role='owner' and status='active'")
    owners = {str(row["id"]) for row in cur.fetchall()}
    if owners != {str(member.membership_id)}:
        raise PermissionDeniedError(details={"reason": "self_decision_not_allowed"})


def _require_assigned_approver_or_owner(step_row: dict[str, object], member: CurrentMember) -> None:
    if member.role is MemberRole.owner:
        return
    if str(step_row["assigned_membership_id"]) == str(member.membership_id):
        return
    raise PermissionDeniedError(details={"reason": "not_assigned_approver"})


def _require_owner(member: CurrentMember) -> None:
    if member.role is not MemberRole.owner:
        raise PermissionDeniedError(details={"reason": "owner_required"})


def _request_group_summaries(
    rows: list[dict[str, object]],
) -> dict[str, RequestGroupSummary]:
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        if isinstance(row.get("request_group"), dict):
            groups.setdefault(str(row["request_group_id"]), []).append(row)
    summaries = {}
    for siblings in groups.values():
        siblings.sort(
            key=lambda r: (
                datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")),
                str(r["id"]),
            )
        )
        group = siblings[0]["request_group"]
        for position, row in enumerate(siblings, 1):
            summaries[str(row["id"])] = RequestGroupSummary(
                id=group["id"],
                rfq_id=group["rfq_id"],
                position=position,
                size=len(siblings),
                combined_total=_money(
                    group["combined_total_amount"], group["combined_total_currency"]
                ),
                best_single_total=_money(
                    group["best_single_total_amount"], group["best_single_total_currency"]
                ),
                saving=_money(group["saving_amount"], group["saving_currency"]),
                sibling_request_ids=[UUID(str(s["id"])) for s in siblings if s is not row],
                siblings=[
                    RequestGroupSibling(
                        id=UUID(str(s["id"])),
                        position=index,
                        supplier_name=s.get("supplier_name"),
                    )
                    for index, s in enumerate(siblings, 1)
                    if s is not row
                ],
            )
    return summaries


def _purchase_request(
    row: dict[str, object],
    line_rows: list[dict[str, object]],
    step_row: dict[str, object] | None,
    *,
    budget_status: BudgetStatus | None = None,
    quoted_prices: dict[UUID, QuotedPrice] | None = None,
    requester: MemberContact | None = None,
    assignee: MemberContact | None = None,
    auto_prepared: AutoPreparedProvenance | None = None,
    source: RequestSource | None = None,
    request_group: RequestGroupSummary | None = None,
) -> PurchaseRequest:
    # Keep recorded decisions as history, but never advertise a stale pending assignee.
    if step_row and step_row["status"] == "pending" and row["status"] in TERMINAL_REQUEST_STATUSES:
        step_row = None
    return PurchaseRequest(
        id=UUID(str(row["id"])),
        source_rfq_response_id=(
            UUID(str(row["source_rfq_response_id"])) if row.get("source_rfq_response_id") else None
        ),
        source=source,
        request_group=request_group,
        auto_prepared=auto_prepared,
        branch_id=UUID(str(row["branch_id"])),
        cost_centre_id=(UUID(str(row["cost_centre_id"])) if row.get("cost_centre_id") else None),
        requested_by_membership_id=UUID(str(row["requested_by_membership_id"])),
        requester_name=requester.name if requester else None,
        requester_email=requester.email if requester else None,
        required_by_date=_parse_date(row["required_by_date"]),
        status=str(row["status"]),
        lines=[_purchase_request_line(lr, quoted_prices or {}) for lr in line_rows],
        estimated_total=_money(
            row.get("estimated_total_amount"),
            row.get("estimated_total_currency"),
        ),
        has_incomplete_estimate=bool(row.get("has_incomplete_estimate", False)),
        budget_status=budget_status,
        approval_step=(
            _approval_step(
                step_row,
                requester_membership_id=UUID(str(row["requested_by_membership_id"])),
                assignee=assignee,
            )
            if step_row
            else None
        ),
        submitted_at=row.get("submitted_at"),
        withdrawn_at=row.get("withdrawn_at"),
        delivered_at=row.get("delivered_at"),
        delivery_confirmed_by_membership_id=(
            UUID(str(row["delivery_confirmed_by_membership_id"]))
            if row.get("delivery_confirmed_by_membership_id")
            else None
        ),
        has_delivery_discrepancy=bool(row.get("has_delivery_discrepancy", False)),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


def _purchase_request_line(
    row: dict[str, object],
    quoted_prices: dict[UUID, QuotedPrice] | None = None,
) -> PurchaseRequestLine:
    quoted = (quoted_prices or {}).get(UUID(str(row["workspace_product_id"])))
    return PurchaseRequestLine(
        id=UUID(str(row["id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        quantity=_decimal(row["quantity"], scale=6),
        quantity_received=(
            _decimal(row["quantity_received"], scale=6)
            if row.get("quantity_received") is not None
            else None
        ),
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
        quoted_unit_price=_money(quoted.amount, quoted.currency) if quoted else None,
        quoted_prices_include_vat=quoted.prices_include_vat if quoted else False,
        quoted_vat_rate=_decimal(quoted.vat_rate, scale=4)
        if quoted and quoted.prices_include_vat and quoted.vat_rate is not None
        else None,
        quoted_net_unit_price=(
            _money(net_unit_price(quoted.amount, quoted.vat_rate), quoted.currency)
            if quoted and quoted.prices_include_vat and quoted.vat_rate is not None
            else _money(quoted.amount, quoted.currency)
            if quoted and not quoted.prices_include_vat
            else None
        ),
        product_name=str(row["product_name"]) if row.get("product_name") is not None else None,
        base_unit=str(row["base_unit"]) if row.get("base_unit") is not None else None,
        pack_base_quantity=(
            _decimal(row["pack_base_quantity"], scale=6)
            if row.get("pack_base_quantity") is not None
            else None
        ),
    )


def _member_contact(row: dict[str, object]) -> MemberContact:
    email, name = row.get("email"), row.get("display_name")
    return MemberContact(str(email) if email else None, str(name) if name else None)


def _replay_group_response(rows: list[dict[str, object]]) -> list[PurchaseRequest]:
    responses = [PurchaseRequest.model_validate(row) for row in rows]
    for request in responses:
        step = request.approval_step
        if step is not None:
            # Older audit snapshots do not carry the derived flag.
            step.self_approval = (
                step.assigned_membership_id
                if step.status == "pending"
                else step.decided_by_membership_id
            ) == request.requested_by_membership_id
    return responses


def _approval_step(
    row: dict[str, object], *, requester_membership_id: UUID, assignee: MemberContact | None = None
) -> ApprovalStep:
    return ApprovalStep(
        self_approval=str(
            row["assigned_membership_id"]
            if str(row["status"]) == "pending"
            else row.get("decided_by_membership_id")
        )
        == str(requester_membership_id),
        id=UUID(str(row["id"])),
        assigned_membership_id=UUID(str(row["assigned_membership_id"])),
        assigned_name=assignee.name if assignee else None,
        assigned_email=assignee.email if assignee else None,
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


def _low_stock_report(row: dict[str, object]) -> LowStockReport:
    """PostgREST decodes `numeric(18,6)` as a JSON number, not a string, so `count_remaining`
    must go through `_decimal()` here — passing the raw row straight into
    `LowStockReport.model_validate()` fails validation for any row that actually has a count,
    since the schema's `count_remaining` is a strict, pattern-matched string.
    """
    return LowStockReport(
        id=UUID(str(row["id"])),
        branch_id=UUID(str(row["branch_id"])),
        member_id=UUID(str(row["member_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        count_remaining=(
            _decimal(row["count_remaining"], scale=6)
            if row.get("count_remaining") is not None
            else None
        ),
        created_at=row["created_at"],
    )


def _quality_issue(row: dict[str, object], *, photos: list[QualityIssuePhoto]) -> QualityIssue:
    return QualityIssue(
        id=UUID(str(row["id"])),
        purchase_request_id=UUID(str(row["purchase_request_id"])),
        reported_by_membership_id=UUID(str(row["reported_by_membership_id"])),
        description=str(row["description"]),
        photos=photos,
        created_at=row["created_at"],
    )


def _quality_issue_photo(row: dict[str, object], *, url: str) -> QualityIssuePhoto:
    return QualityIssuePhoto(
        id=UUID(str(row["id"])),
        delivery_quality_issue_id=UUID(str(row["delivery_quality_issue_id"])),
        url=url,
        created_at=row["created_at"],
    )


def _threshold_rule(row: dict[str, object]) -> ThresholdRule:
    return ThresholdRule(
        id=UUID(str(row["id"])),
        branch_id=(UUID(str(row["branch_id"])) if row.get("branch_id") else None),
        min_amount=_decimal(row["min_amount"], scale=4),
        max_amount=(
            _decimal(row["max_amount"], scale=4) if row.get("max_amount") is not None else None
        ),
        currency=str(row["currency"]),
        approver_membership_id=UUID(str(row["approver_membership_id"])),
        created_by=UUID(str(row["created_by"])),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


def _threshold_rule_row(row: dict[str, object]) -> ThresholdRuleRow:
    return ThresholdRuleRow(
        id=UUID(str(row["id"])),
        branch_id=(UUID(str(row["branch_id"])) if row.get("branch_id") else None),
        min_amount=Decimal(str(row["min_amount"])),
        max_amount=(Decimal(str(row["max_amount"])) if row.get("max_amount") is not None else None),
        currency=str(row["currency"]),
        approver_membership_id=UUID(str(row["approver_membership_id"])),
    )


def _approval_delegation(row: dict[str, object]) -> ApprovalDelegation:
    return ApprovalDelegation(
        id=UUID(str(row["id"])),
        delegator_membership_id=UUID(str(row["delegator_membership_id"])),
        delegate_membership_id=UUID(str(row["delegate_membership_id"])),
        starts_on=_parse_date(row["starts_on"]),
        ends_on=_parse_date(row["ends_on"]),
        created_at=row["created_at"],
    )


def _budget_row(row: dict[str, object]) -> BudgetRow:
    return BudgetRow(
        id=UUID(str(row["id"])),
        amount=Decimal(str(row["amount"])),
        currency=str(row["currency"]),
        period=str(row["period"]),
        period_start=_parse_date(row["period_start"]),
        scope=str(row["scope"]),
        branch_id=(UUID(str(row["branch_id"])) if row.get("branch_id") else None),
        cost_centre_id=(UUID(str(row["cost_centre_id"])) if row.get("cost_centre_id") else None),
    )


def _spend_row(row: dict[str, object]) -> SpendRow:
    return SpendRow(
        request_id=UUID(str(row["id"])),
        amount=Decimal(str(row["estimated_total_amount"])),
        currency=str(row["estimated_total_currency"]),
        branch_id=UUID(str(row["branch_id"])),
        cost_centre_id=(UUID(str(row["cost_centre_id"])) if row.get("cost_centre_id") else None),
        required_by_date=_parse_date(row["required_by_date"]),
    )


def _delegation_row(row: dict[str, object]) -> DelegationRow:
    created_at = row["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if not isinstance(created_at, datetime):
        raise ServiceUnavailableError(details={"reason": "invalid_datetime"})
    return DelegationRow(
        id=UUID(str(row["id"])),
        delegator_membership_id=UUID(str(row["delegator_membership_id"])),
        delegate_membership_id=UUID(str(row["delegate_membership_id"])),
        starts_on=_parse_date(row["starts_on"]),
        ends_on=_parse_date(row["ends_on"]),
        created_at=created_at,
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


def _validate_decision_comment(decision: str, comment: str | None) -> None:
    if comment is not None and len(comment) > 2000:
        raise UnprocessableEntityError(details={"reason": "comment_too_long"})
    if decision == "rejected" and (comment is None or not comment.strip()):
        raise UnprocessableEntityError(details={"reason": "comment_required"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _quality_issue_storage_path(*, tenant_id: UUID, issue_id: UUID, filename: str) -> str:
    name = safe_object_name(filename)
    return f"tenants/{tenant_id}/quality-issues/{issue_id}/{uuid4()}/{name}"


def _signed_url(result: object) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("signedURL", "signed_url", "url"):
            value = result.get(key)
            if value:
                return str(value)
    raise ServiceUnavailableError(details={"dependency": "supabase_storage"})


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


def _one_row_or_not_found(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": f"{resource}_write_ambiguous"})
    return rows[0]


def _one_row_or_conflict(data: object, *, reason: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 0:
        raise ConflictError(details={"reason": reason})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": "write_ambiguous"})
    return rows[0]


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


_APPROVAL_SORT_COLUMNS = {
    "submitted_desc": ("ast.created_at", "desc"),
    "submitted_asc": ("ast.created_at", "asc"),
    "required_by_asc": ("pr.required_by_date", "asc"),
    "total_desc": ("pr.estimated_total_amount", "desc"),
    "total_asc": ("pr.estimated_total_amount", "asc"),
}


def _pending_approval_query(
    *,
    sort: PendingApprovalSort,
    branch_id: UUID | None,
    membership_id: UUID,
    is_owner: bool,
    is_sole_owner: bool,
    boundary: tuple[str | None, UUID] | None,
    limit: int,
    count: bool = False,
) -> tuple[str, list[object]]:
    column, direction = _APPROVAL_SORT_COLUMNS[sort]
    predicates = ["ast.status = 'pending'"]
    params: list[object] = []
    for status in sorted(TERMINAL_REQUEST_STATUSES):
        predicates.append("pr.status <> %s")
        params.append(status)
    if not is_owner:
        predicates.append("ast.assigned_membership_id = %s")
        params.append(membership_id)
    if not is_sole_owner:
        predicates.append("pr.requested_by_membership_id <> %s")
        params.append(membership_id)
    if branch_id is not None:
        predicates.append("pr.branch_id = %s")
        params.append(branch_id)
    if boundary is not None and not count:
        value, step_id = boundary
        if value is None:
            predicates.append(f"({column} is null and ast.id > %s)")
            params.append(step_id)
        else:
            operator = "<" if direction == "desc" else ">"
            predicates.append(
                f"({column} {operator} %s or ({column} = %s and ast.id > %s) or {column} is null)"
            )
            params.extend([value, value, step_id])
    projection = "count(*) as total" if count else f"ast.*, {column} as sort_value"
    query = (
        f"select {projection} from approval_step ast "
        "join purchase_request pr on pr.id = ast.purchase_request_id "
        "where " + " and ".join(predicates)
    )
    if not count:
        query += f" order by {column} {direction} nulls last, ast.id asc limit %s"
        params.append(limit + 1)
    return query, params


def _encode_approval_cursor(
    value: str | None,
    step_id: UUID,
    *,
    sort: PendingApprovalSort = "submitted_desc",
    branch_id: UUID | None = None,
) -> str:
    raw = json.dumps(
        {
            "sort": sort,
            "value": value,
            "id": str(step_id),
            "branch_id": str(branch_id) if branch_id else None,
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_approval_cursor(
    cursor: str | None,
    *,
    sort: PendingApprovalSort = "submitted_desc",
    branch_id: UUID | None = None,
) -> tuple[str | None, UUID] | None:
    if cursor is None:
        return None
    try:
        raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid cursor payload")
        # Existing unfiltered default-sort cursors remain valid across deployment.
        if "sort" not in payload and "created_at" in payload:
            payload = {
                **payload,
                "sort": "submitted_desc",
                "branch_id": None,
                "value": payload["created_at"],
            }
        if payload["sort"] != sort or payload["branch_id"] != (
            str(branch_id) if branch_id else None
        ):
            raise ValueError("cursor filter mismatch")
        value, step_id = payload["value"], payload["id"]
        if not isinstance(step_id, str) or (value is not None and not isinstance(value, str)):
            raise ValueError("invalid cursor fields")
        if sort.startswith("submitted"):
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is None:
                raise ValueError("cursor timestamp requires a timezone")
            value = (
                timestamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
            )
        elif value is not None:
            if sort == "required_by_asc":
                value = date.fromisoformat(value).isoformat()
            # purchase_request.estimated_total_amount is numeric(18, 4).
            elif (
                not value.isascii()
                or re.fullmatch(r"[+-]?[0-9]{1,14}(?:\.[0-9]{1,4})?", value) is None
            ):
                raise ValueError("invalid cursor amount")
        return value, UUID(step_id)
    except (KeyError, ValueError, TypeError, OverflowError, ArithmeticError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc


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
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset


def _write_error(
    exc: APIError,
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    code = _api_error_code(exc)
    if code in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    if code == "23505":
        return ConflictError(details={"reason": "duplicate"})
    return ServiceUnavailableError(details={"dependency": "database"})


def _map_psycopg_error(
    exc: psycopg.Error,
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    code = getattr(exc, "sqlstate", None)
    if code in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    if code == "23505":
        return ConflictError(details={"reason": "duplicate"})
    return ServiceUnavailableError(details={"dependency": "database"})


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None


def _insert_group_requests(conn: psycopg.Connection, rows: list[dict[str, object]]) -> None:
    """Single batched insert; separate seam lets rollback tests inject a real constraint error."""
    conn.execute(
        """
        insert into purchase_request
          (id,tenant_id,branch_id,cost_centre_id,requested_by_membership_id,
           required_by_date,status,source_rfq_response_id,request_group_id,
           estimated_total_amount,estimated_total_currency,has_incomplete_estimate)
        select id,tenant_id,branch_id,cost_centre_id,requested_by_membership_id,
               required_by_date,'draft',source_rfq_response_id,request_group_id,
               estimated_total_amount,estimated_total_currency,false
        from jsonb_to_recordset(%s) as x(
          id uuid,tenant_id uuid,branch_id uuid,cost_centre_id uuid,
          requested_by_membership_id uuid,required_by_date date,
          source_rfq_response_id uuid,request_group_id uuid,
          estimated_total_amount numeric,estimated_total_currency text)
        """,
        (Jsonb(rows),),
    )


def create_requests_for_group(
    conn: psycopg.Connection,
    member: CurrentMember,
    group_row: dict[str, object],
    allocations: list[dict[str, object]],
) -> tuple[list[UUID], Decimal]:
    """Insert the group, drafts and RFQ-ordered pack lines on the caller's transaction.

    The source-snapshot trigger (#325) captures RFQ, quotation and supplier on INSERT.
    Allocations carry the frozen RFQ pack sizes and destination chosen by the buyer.
    The group's approval total is the sum of these draft estimates; solver totals may
    differ through pack-price rounding, quantity tiers and supplier delivery fees.
    """
    requests: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []
    request_ids: list[UUID] = []
    combined = Decimal(0)
    for allocation in allocations:
        request_id = uuid4()
        request_ids.append(request_id)
        allocated_lines = allocation["lines"]
        estimates = estimate_from_source_response(
            conn,
            rfq_response_id=allocation["response_id"],
            product_ids=[line["workspace_product_id"] for line in allocated_lines],
        )
        total = Decimal(0)
        for position, line in enumerate(allocated_lines):
            estimate = estimates.get(line["workspace_product_id"])
            if (
                estimate is None
                or estimate.unit_price_amount is None
                or estimate.unit_price_currency != group_row["combined_total_currency"]
                or estimate.source_landed_cost_id != line["source_landed_cost_id"]
            ):
                raise ConflictError(details={"reason": "split_stale"})
            total += estimate.unit_price_amount * line["quantity"]
            lines.append(
                {
                    "tenant_id": str(member.tenant_id),
                    "purchase_request_id": str(request_id),
                    "workspace_product_id": str(line["workspace_product_id"]),
                    "quantity": str(line["quantity"]),
                    "pack_base_quantity": str(line["pack_base_quantity"]),
                    "position": position,
                    "amount": str(estimate.unit_price_amount),
                    "currency": estimate.unit_price_currency,
                    "landed_cost_id": str(estimate.source_landed_cost_id)
                    if estimate.source_landed_cost_id
                    else None,
                }
            )
        combined += total
        requests.append(
            {
                "id": str(request_id),
                "tenant_id": str(member.tenant_id),
                "branch_id": str(group_row["branch_id"]),
                "cost_centre_id": str(allocation["cost_centre_id"])
                if allocation["cost_centre_id"]
                else None,
                "requested_by_membership_id": str(member.membership_id),
                "required_by_date": str(allocation["required_by_date"]),
                "source_rfq_response_id": str(allocation["response_id"]),
                "request_group_id": str(group_row["id"]),
                "estimated_total_amount": str(total),
                "estimated_total_currency": group_row["combined_total_currency"],
            }
        )
    conn.execute(
        """
        insert into purchase_request_group
          (id,tenant_id,rfq_id,basket_split_job_id,branch_id,combined_total_amount,
           combined_total_currency,best_single_total_amount,best_single_total_currency,
           saving_amount,saving_currency,idempotency_key,created_by_membership_id)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            group_row["id"],
            member.tenant_id,
            group_row["rfq_id"],
            group_row["basket_split_job_id"],
            group_row["branch_id"],
            combined,
            group_row["combined_total_currency"],
            group_row["best_single_total_amount"],
            group_row["best_single_total_currency"],
            group_row["saving_amount"],
            group_row["saving_currency"],
            group_row["idempotency_key"],
            member.membership_id,
        ),
    )
    _insert_group_requests(conn, requests)
    conn.execute(
        """
        insert into purchase_request_line
          (tenant_id,purchase_request_id,workspace_product_id,quantity,position,
           pack_base_quantity,estimated_unit_price_amount,estimated_unit_price_currency,
           estimated_unit_price_source_landed_cost_id,estimated_at)
        select tenant_id,purchase_request_id,workspace_product_id,quantity,position,
               pack_base_quantity,amount,currency,landed_cost_id,now()
        from jsonb_to_recordset(%s) as x(
          tenant_id uuid,purchase_request_id uuid,workspace_product_id uuid,quantity numeric,
          position integer,pack_base_quantity numeric,amount numeric,currency text,
          landed_cost_id uuid)
        """,
        (Jsonb(lines),),
    )
    return request_ids, combined


def validate_group_destination(
    conn: psycopg.Connection, member: CurrentMember, branch_id: UUID, cost_centre_id: UUID | None
) -> None:
    """Match request branch-write scope; destination identifiers are read under member RLS."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select exists(select 1 from branch where id=%s) as branch_found,
                   (%s::uuid is null or exists(select 1 from cost_centre where id=%s))
                     as cost_centre_found,
                   (current_membership_role()='owner'
                    or not exists(select 1 from branch_role_assignment where membership_id=%s)
                    or exists(select 1 from branch_role_assignment
                              where membership_id=%s and branch_id=%s)) as branch_allowed
            """,
            (
                branch_id,
                cost_centre_id,
                cost_centre_id,
                member.membership_id,
                member.membership_id,
                branch_id,
            ),
        )
        destination = cur.fetchone()
    if not destination["branch_found"]:
        raise NotFoundError(details={"resource": "branch"})
    if not destination["cost_centre_found"]:
        raise NotFoundError(details={"resource": "cost_centre"})
    if not destination["branch_allowed"]:
        raise PermissionDeniedError(details={"reason": "branch_not_assigned"})
