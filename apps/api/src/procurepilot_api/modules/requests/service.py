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
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.requests.budget_status import (
    BudgetRow,
    SpendRow,
    compute_budget_status,
)
from procurepilot_api.modules.requests.routing import (
    DelegationRow,
    ThresholdRuleRow,
    resolve_approver,
)
from procurepilot_api.modules.requests.schemas import (
    ApprovalDecisionInput,
    ApprovalDelegation,
    ApprovalDelegationCreate,
    ApprovalDelegationList,
    ApprovalStep,
    BudgetStatus,
    LowStockReport,
    LowStockReportCreate,
    LowStockReportList,
    Money,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestLine,
    PurchaseRequestList,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
    ThresholdRule,
    ThresholdRuleCreate,
    ThresholdRuleList,
    ThresholdRuleUpdate,
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
THRESHOLD_RULE_COLUMNS = (
    "id,branch_id,min_amount,max_amount,currency,approver_membership_id,"
    "created_by,created_at,updated_at"
)
DELEGATION_COLUMNS = (
    "id,delegator_membership_id,delegate_membership_id,starts_on,ends_on,"
    "created_at"
)
BUDGET_COLUMNS = (
    "id,amount,currency,period,period_start,scope,branch_id,cost_centre_id"
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
        return self._purchase_request_with_budget_status(
            client, request_row, line_rows, step_row=None
        )

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
        return self._purchase_request_with_budget_status(
            client, request_row, line_rows, step_row
        )

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
            self._purchase_request_with_budget_status(
                client,
                row,
                lines_by_request.get(str(row["id"]), []),
                steps_by_request.get(str(row["id"])),
            )
            for row in visible
        ]
        return PurchaseRequestList(items=items, next_cursor=next_cursor)

    def list_pending_approvals(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = 50,
    ) -> PurchaseRequestList:
        client = authenticated_client(self._settings, bearer_token)
        capped = _cap_limit(limit)
        offset = _decode_cursor(cursor)

        try:
            query = (
                client.table("approval_step")
                .select(STEP_COLUMNS)
                .eq("status", "pending")
            )
            if member.role is not MemberRole.owner:
                query = query.eq(
                    "assigned_membership_id", str(member.membership_id)
                )
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

        step_rows = _rows(response.data)
        visible_steps = step_rows[:capped]
        next_cursor = (
            _encode_cursor(offset + capped)
            if len(step_rows) > capped
            else None
        )
        if not visible_steps:
            return PurchaseRequestList(items=[], next_cursor=next_cursor)

        request_ids = [
            str(step["purchase_request_id"]) for step in visible_steps
        ]
        request_rows = self._fetch_requests_batch(client, request_ids)
        lines_by_request = self._fetch_lines_batch(client, request_ids)
        steps_by_request = {
            str(step["purchase_request_id"]): step for step in visible_steps
        }

        items = [
            self._purchase_request_with_budget_status(
                client,
                row,
                lines_by_request.get(str(row["id"]), []),
                steps_by_request.get(str(row["id"])),
            )
            for row in request_rows
        ]
        return PurchaseRequestList(items=items, next_cursor=next_cursor)

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
            response = (
                client.table("low_stock_report").insert(row_data).execute()
            )
        except APIError as exc:
            if idempotency_key is not None and _api_error_code(exc) == "23505":
                existing = self._fetch_low_stock_report_by_key(
                    client, idempotency_key=idempotency_key
                )
                return LowStockReport.model_validate(existing), False
            raise _write_error(exc) from exc

        row = _one_row(response.data, reason="low_stock_report_write_failed")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.low_stock_report_created",
            target={"low_stock_report_id": str(row["id"])},
        )
        return LowStockReport.model_validate(row), True

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
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return _one_row(
            response.data, reason="low_stock_report_idempotency_lookup_failed"
        )

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
                query = query.eq(
                    "workspace_product_id", str(workspace_product_id)
                )
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
        items = [LowStockReport.model_validate(row) for row in visible]
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
        return self._purchase_request_with_budget_status(
            client, request_row, new_line_rows, step_row
        )

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
        routed_step = self._create_submission_approval_step(
            client,
            bearer_token=bearer_token,
            member=member,
            request_row=request_row,
        )
        frozen_lines = self._fetch_lines_for(client, rid)

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="requests.purchase_request_submitted",
            target={"purchase_request_id": rid},
        )
        return self._purchase_request_with_budget_status(
            client, request_row, frozen_lines, routed_step
        )

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
        return self._purchase_request_with_budget_status(
            client, request_row, line_rows, step_row
        )

    def approve_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: ApprovalDecisionInput,
    ) -> PurchaseRequest:
        return self._decide_request(
            bearer_token=bearer_token,
            member=member,
            request_id=request_id,
            payload=payload,
            decision="approved",
        )

    def reject_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        request_id: UUID,
        payload: ApprovalDecisionInput,
    ) -> PurchaseRequest:
        return self._decide_request(
            bearer_token=bearer_token,
            member=member,
            request_id=request_id,
            payload=payload,
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
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        rows = _rows(response.data)
        return ThresholdRuleList(
            items=[_threshold_rule(row) for row in rows[:capped]],
            next_cursor=(
                _encode_cursor(offset + capped)
                if len(rows) > capped
                else None
            ),
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
                            str(payload.branch_id)
                            if payload.branch_id is not None
                            else None
                        ),
                        "min_amount": payload.min_amount,
                        "max_amount": payload.max_amount,
                        "currency": payload.currency,
                        "approver_membership_id": str(
                            payload.approver_membership_id
                        ),
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
                client.table("threshold_rule")
                .update(updates)
                .eq("id", str(rule_id))
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        row = _one_row_or_not_found(
            response.data, resource="threshold_rule"
        )
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
            response = (
                client.table("threshold_rule")
                .delete()
                .eq("id", str(rule_id))
                .execute()
            )
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
                raise PermissionDeniedError(
                    details={"reason": "not_delegator_or_owner"}
                )
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
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
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
        if member.role is not MemberRole.owner and str(delegator_id) != str(
            member.membership_id
        ):
            raise PermissionDeniedError(
                details={"reason": "not_delegator_or_owner"}
            )

        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("approval_delegation")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "delegator_membership_id": str(delegator_id),
                        "delegate_membership_id": str(
                            payload.delegate_membership_id
                        ),
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
        if member.role is not MemberRole.owner and str(
            existing["delegator_membership_id"]
        ) != str(member.membership_id):
            raise PermissionDeniedError(
                details={"reason": "not_delegator_or_owner"}
            )
        try:
            response = (
                client.table("approval_delegation")
                .delete()
                .eq("id", str(delegation_id))
                .execute()
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
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        rows_by_id = {str(row["id"]): row for row in _rows(response.data)}
        return [
            rows_by_id[request_id]
            for request_id in request_ids
            if request_id in rows_by_id
        ]

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

    def _fetch_threshold_rules(
        self, client: Client
    ) -> list[ThresholdRuleRow]:
        try:
            response = (
                client.table("threshold_rule")
                .select(THRESHOLD_RULE_COLUMNS)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return [_threshold_rule_row(row) for row in _rows(response.data)]

    def _fetch_active_delegations(
        self, client: Client, *, as_of: date
    ) -> list[DelegationRow]:
        try:
            response = (
                client.table("approval_delegation")
                .select(DELEGATION_COLUMNS)
                .lte("starts_on", as_of.isoformat())
                .gte("ends_on", as_of.isoformat())
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
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
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        row = _one_row(response.data, reason="owner_membership_not_found")
        return UUID(str(row["id"]))

    def _fetch_removed_membership_ids(self, client: Client) -> set[UUID]:
        try:
            response = (
                client.table("membership")
                .select("id")
                .neq("status", "active")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return {UUID(str(row["id"])) for row in _rows(response.data)}

    def _fetch_budget_rows(self, client: Client) -> list[BudgetRow]:
        try:
            response = client.table("budget").select(BUDGET_COLUMNS).execute()
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return [_budget_row(row) for row in _rows(response.data)]

    def _fetch_committed_spend_rows(self, client: Client) -> list[SpendRow]:
        try:
            response = (
                client.table("purchase_request")
                .select(
                    "id,branch_id,cost_centre_id,required_by_date,"
                    "estimated_total_amount,estimated_total_currency,status"
                )
                .in_("status", ["submitted", "approved"])
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        spend_rows = []
        for row in _rows(response.data):
            if (
                row.get("estimated_total_amount") is None
                or row.get("estimated_total_currency") is None
            ):
                continue
            spend_rows.append(_spend_row(row))
        return spend_rows

    def _fetch_delegation(
        self, client: Client, delegation_id: UUID
    ) -> dict[str, object]:
        try:
            response = (
                client.table("approval_delegation")
                .select(DELEGATION_COLUMNS)
                .eq("id", str(delegation_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc
        return _one_row_or_not_found(
            response.data, resource="approval_delegation"
        )

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
            as_of=as_of,
        )
        try:
            response = (
                client.table("approval_step")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "purchase_request_id": str(request_row["id"]),
                        "assigned_membership_id": str(
                            resolved.assigned_membership_id
                        ),
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
                    "assigned_membership_id": str(
                        resolved.assigned_membership_id
                    ),
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
            pending_response = (
                client.table("approval_step")
                .select("id,purchase_request_id")
                .eq("assigned_membership_id", str(removed_membership_id))
                .eq("status", "pending")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(
                details={"dependency": "database"}
            ) from exc

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
    ) -> PurchaseRequest:
        client = authenticated_client(self._settings, bearer_token)
        request_row = self._fetch_request(client, request_id)
        if str(request_row["status"]) != "submitted":
            raise ConflictError(details={"reason": "not_submitted"})

        rid = str(request_id)
        step_row = self._fetch_step(client, rid)
        if step_row is None or str(step_row["status"]) != "pending":
            raise ConflictError(details={"reason": "no_pending_approval"})
        _require_assigned_approver_or_owner(step_row, member)

        now = _now_iso()
        # Update the request BEFORE the step. supabase-py has no multi-statement transaction, so
        # these two writes cannot be truly atomic here — a fully race-safe version needs a DB
        # function (tracked as follow-up). Given that, the request's `status = 'submitted'` guard
        # is the authoritative gate: if a concurrent withdrawal already flipped it, this update
        # matches zero rows and we raise before touching the step, leaving the step `pending`
        # rather than stranding a `decided` step on a non-submitted request (which would make the
        # request permanently undecidable).
        try:
            request_response = (
                client.table("purchase_request")
                .update({"status": decision, "updated_at": now})
                .eq("id", rid)
                .eq("status", "submitted")
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        decided_request = _one_row_or_conflict(
            request_response.data, reason="not_submitted"
        )

        try:
            step_response = (
                client.table("approval_step")
                .update(
                    {
                        "status": decision,
                        "comment": payload.comment,
                        "decided_by_membership_id": str(
                            member.membership_id
                        ),
                        "decided_at": now,
                    }
                )
                .eq("id", str(step_row["id"]))
                .eq("status", "pending")
                .execute()
            )
        except APIError as exc:
            raise _write_error(exc) from exc
        decided_step = _one_row_or_conflict(
            step_response.data, reason="no_pending_approval"
        )

        line_rows = self._fetch_lines_for(client, rid)
        self._record(
            bearer_token=bearer_token,
            member=member,
            action=f"requests.approval_step_{decision}",
            target={
                "purchase_request_id": rid,
                "approval_step_id": str(decided_step["id"]),
                "decided_by_membership_id": str(member.membership_id),
            },
        )
        return self._purchase_request_with_budget_status(
            client, decided_request, line_rows, decided_step
        )

    def _purchase_request_with_budget_status(
        self,
        client: Client,
        request_row: dict[str, object],
        line_rows: list[dict[str, object]],
        step_row: dict[str, object] | None,
    ) -> PurchaseRequest:
        return _purchase_request(
            request_row,
            line_rows,
            step_row,
            budget_status=self._budget_status_for(client, request_row),
        )

    def _budget_status_for(
        self,
        client: Client,
        request_row: dict[str, object],
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
                UUID(str(request_row["cost_centre_id"]))
                if request_row.get("cost_centre_id")
                else None
            ),
            required_by=_parse_date(request_row["required_by_date"]),
            budgets=self._fetch_budget_rows(client),
            committed_spend=self._fetch_committed_spend_rows(client),
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


def _require_assigned_approver_or_owner(
    step_row: dict[str, object], member: CurrentMember
) -> None:
    if member.role is MemberRole.owner:
        return
    if str(step_row["assigned_membership_id"]) == str(member.membership_id):
        return
    raise PermissionDeniedError(details={"reason": "not_assigned_approver"})


def _require_owner(member: CurrentMember) -> None:
    if member.role is not MemberRole.owner:
        raise PermissionDeniedError(details={"reason": "owner_required"})


def _purchase_request(
    row: dict[str, object],
    line_rows: list[dict[str, object]],
    step_row: dict[str, object] | None,
    *,
    budget_status: BudgetStatus | None = None,
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
        budget_status=budget_status,
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


def _threshold_rule(row: dict[str, object]) -> ThresholdRule:
    return ThresholdRule(
        id=UUID(str(row["id"])),
        branch_id=(
            UUID(str(row["branch_id"])) if row.get("branch_id") else None
        ),
        min_amount=_decimal(row["min_amount"], scale=4),
        max_amount=(
            _decimal(row["max_amount"], scale=4)
            if row.get("max_amount") is not None
            else None
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
        branch_id=(
            UUID(str(row["branch_id"])) if row.get("branch_id") else None
        ),
        min_amount=Decimal(str(row["min_amount"])),
        max_amount=(
            Decimal(str(row["max_amount"]))
            if row.get("max_amount") is not None
            else None
        ),
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
        branch_id=(
            UUID(str(row["branch_id"])) if row.get("branch_id") else None
        ),
        cost_centre_id=(
            UUID(str(row["cost_centre_id"]))
            if row.get("cost_centre_id")
            else None
        ),
    )


def _spend_row(row: dict[str, object]) -> SpendRow:
    return SpendRow(
        request_id=UUID(str(row["id"])),
        amount=Decimal(str(row["estimated_total_amount"])),
        currency=str(row["estimated_total_currency"]),
        branch_id=UUID(str(row["branch_id"])),
        cost_centre_id=(
            UUID(str(row["cost_centre_id"]))
            if row.get("cost_centre_id")
            else None
        ),
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
