from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import psycopg
from postgrest.exceptions import APIError
from psycopg.rows import dict_row
from pydantic import BaseModel, ValidationError
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
from procurepilot_api.modules.orders.schemas import (
    DeliveryReceipt,
    DeliveryReceiptCreate,
    DeliveryReceiptLine,
    OrderEvidenceProjection,
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderDraftUpdate,
    PurchaseOrderLine,
    PurchaseOrderList,
    RequestAllocation,
    RequestLineAllocation,
    SupplierConfirmation,
    SupplierConfirmationCreate,
    SupplierConfirmationLine,
)
from procurepilot_api.modules.orders.validation import (
    build_lifecycle_summary,
    validate_confirmation_against_order,
    validate_receipt_against_order,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

LOGGER = logging.getLogger(__name__)

ORDER_COLUMNS = "*"
ORDER_HEADER_COLUMNS = (
    "id,tenant_id,order_number,supplier_id,status,order_date,expected_delivery_date,"
    "total_amount,total_currency,tax_amount,tax_currency,source_kind,source_reference,"
    "source_hash,source_request_id,created_by,created_at,updated_at,submit_idempotency_key,edit_idempotency_key,cancel_idempotency_key"
)
ORDER_LINE_COLUMNS = (
    "id,line_number,workspace_product_id,description,ordered_quantity,base_unit,"
    "unit_price_amount,unit_price_currency,tax_amount,tax_currency,line_total_amount,"
    "line_total_currency,source_request_line_id"
)
CONFIRMATION_COLUMNS = (
    "id,tenant_id,purchase_order_id,supplier_reference,confirmed_at,expected_delivery_date,"
    "source_kind,source_reference,source_hash,recorded_by,created_at"
)
CONFIRMATION_LINE_COLUMNS = (
    "id,purchase_order_line_id,confirmed_quantity,confirmed_unit_price_amount,"
    "confirmed_unit_price_currency"
)
RECEIPT_COLUMNS = (
    "id,tenant_id,purchase_order_id,receipt_reference,receipt_date,received_by,source_kind,"
    "source_reference,source_hash,created_at"
)
RECEIPT_LINE_COLUMNS = "id,purchase_order_line_id,received_quantity"
WRITE_ROLES = {MemberRole.owner, MemberRole.buyer}


class OrdersService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_order(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: PurchaseOrderCreate,
        idempotency_key: UUID | None,
    ) -> tuple[PurchaseOrder, bool]:
        self._require_write(member, idempotency_key)

        request_lines_by_id = {}
        if payload.source_request_id:
            from procurepilot_api.modules.requests.service import RequestsService

            requests_service = RequestsService(self._settings)
            source_request = requests_service.validate_approved_request_for_order(
                bearer_token=bearer_token, member=member, request_id=payload.source_request_id
            )
            request_lines_by_id = {line.id: line for line in source_request.lines}
            for line in payload.lines:
                if not getattr(line, "source_request_line_id", None):
                    raise UnprocessableEntityError(
                        details={"reason": "missing_source_request_line_id"}
                    )
                if line.source_request_line_id not in request_lines_by_id:
                    raise NotFoundError(details={"resource": "purchase_request_line"})
                req_line = request_lines_by_id[line.source_request_line_id]
                if line.workspace_product_id != req_line.workspace_product_id:
                    raise UnprocessableEntityError(details={"reason": "product_mismatch"})
                if line.ordered_quantity <= 0:
                    raise UnprocessableEntityError(details={"reason": "invalid_quantity"})
        else:
            for line in payload.lines:
                if getattr(line, "source_request_line_id", None) is not None:
                    raise UnprocessableEntityError(
                        details={"reason": "orphan_source_request_line_id"}
                    )

        data = {
            "tenant_id": str(member.tenant_id),
            "order_number": payload.order_number,
            "supplier_id": str(payload.supplier_id),
            "status": "draft",
            "order_date": payload.order_date.isoformat(),
            "expected_delivery_date": payload.expected_delivery_date.isoformat()
            if payload.expected_delivery_date
            else None,
            "total_amount": _decimal(payload.total.amount),
            "total_currency": payload.total.currency,
            "tax_amount": _decimal(payload.tax.amount),
            "tax_currency": payload.tax.currency,
            "source_kind": payload.source_kind,
            "source_reference": payload.source_reference,
            "source_hash": payload.source_hash,
            "source_request_id": str(payload.source_request_id)
            if payload.source_request_id
            else None,
            "created_by": str(member.membership_id),
            "submit_idempotency_key": str(idempotency_key),
        }
        with self._transaction(member) as cur:
            if payload.source_request_id:
                self._lock_requests(cur, member.tenant_id, {payload.source_request_id})

                self._assert_request_allocation_available(
                    cur=cur,
                    tenant_id=member.tenant_id,
                    request_lines_by_id=request_lines_by_id,
                    lines=payload.lines,
                )

            cur.execute(
                f"insert into purchase_order ({','.join(data)}) "
                f"values ({','.join(['%s'] * len(data))}) "
                f"on conflict do nothing returning {ORDER_HEADER_COLUMNS}",
                tuple(data.values()),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    f"select {ORDER_HEADER_COLUMNS} from purchase_order "
                    "where tenant_id = %s and submit_idempotency_key = %s for update",
                    (member.tenant_id, idempotency_key),
                )
                row = cur.fetchone()
                if row is not None:
                    order = self._load_order_cursor(cur, UUID(str(row["id"])))
                    return order, False
                raise ConflictError(details={"reason": "order_number_or_idempotency_exists"})
            order_id = UUID(str(row["id"]))
            cur.executemany(
                "insert into purchase_order_line (tenant_id,purchase_order_id,line_number,"
                "workspace_product_id,description,ordered_quantity,base_unit,unit_price_amount,"
                "unit_price_currency,tax_amount,tax_currency,line_total_amount,"
                "line_total_currency,source_request_id,source_request_line_id) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        member.tenant_id,
                        order_id,
                        line.line_number,
                        line.workspace_product_id,
                        line.description,
                        line.ordered_quantity,
                        line.base_unit,
                        line.unit_price.amount,
                        line.unit_price.currency,
                        line.tax.amount,
                        line.tax.currency,
                        line.line_total.amount,
                        line.line_total.currency,
                        payload.source_request_id,
                        line.source_request_line_id,
                    )
                    for line in payload.lines
                ],
            )
            order = self._load_order_cursor(cur, order_id)
            self._audit_cursor(cur, member, "orders.purchase_order_created", order_id)
        return order, True

    def update_draft_order(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        order_id: UUID,
        payload: PurchaseOrderDraftUpdate,
        idempotency_key: UUID,
    ) -> PurchaseOrder:
        self._require_write(member, idempotency_key)

        request_lines_by_id = {}
        if payload.source_request_id:
            from procurepilot_api.modules.requests.service import RequestsService

            requests_service = RequestsService(self._settings)
            source_request = requests_service.validate_approved_request_for_order(
                bearer_token=bearer_token, member=member, request_id=payload.source_request_id
            )
            request_lines_by_id = {line.id: line for line in source_request.lines}
            for line in payload.lines:
                if not getattr(line, "source_request_line_id", None):
                    raise UnprocessableEntityError(
                        details={"reason": "missing_source_request_line_id"}
                    )
                if line.source_request_line_id not in request_lines_by_id:
                    raise NotFoundError(details={"resource": "purchase_request_line"})
                req_line = request_lines_by_id[line.source_request_line_id]
                if line.workspace_product_id != req_line.workspace_product_id:
                    raise UnprocessableEntityError(details={"reason": "product_mismatch"})
                if line.ordered_quantity <= 0:
                    raise UnprocessableEntityError(details={"reason": "invalid_quantity"})
        else:
            for line in payload.lines:
                if getattr(line, "source_request_line_id", None) is not None:
                    raise UnprocessableEntityError(
                        details={"reason": "orphan_source_request_line_id"}
                    )

        with self._transaction(member) as cur:
            cur.execute(
                f"select {ORDER_HEADER_COLUMNS} from purchase_order "
                "where tenant_id = %s and id = %s for update",
                (member.tenant_id, order_id),
            )
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(details={"resource": "purchase_order"})
            if row["status"] != "draft":
                raise ConflictError(details={"reason": "order_not_draft"})
            if row.get("edit_idempotency_key") and str(row["edit_idempotency_key"]) == str(
                idempotency_key
            ):
                return self._load_order_cursor(cur, order_id)
            cur.execute(
                "select 1 from purchase_order where tenant_id = %s "
                "and edit_idempotency_key = %s and id != %s",
                (member.tenant_id, idempotency_key, order_id),
            )
            if cur.fetchone() is not None:
                raise ConflictError(details={"reason": "order_number_or_idempotency_exists"})

            requests_to_lock = set()
            if row.get("source_request_id"):
                requests_to_lock.add(UUID(str(row["source_request_id"])))
            if payload.source_request_id:
                requests_to_lock.add(payload.source_request_id)
            if requests_to_lock:
                self._lock_requests(cur, member.tenant_id, requests_to_lock)

            if payload.source_request_id:
                self._assert_request_allocation_available(
                    cur=cur,
                    tenant_id=member.tenant_id,
                    request_lines_by_id=request_lines_by_id,
                    lines=payload.lines,
                    excluded_order_id=order_id,
                )

            cur.execute(
                "update purchase_order set order_number = %s, supplier_id = %s, order_date = %s, "
                "expected_delivery_date = %s, total_amount = %s, total_currency = %s, "
                "tax_amount = %s, tax_currency = %s, source_kind = %s, source_reference = %s, "
                "source_hash = %s, source_request_id = %s, edit_idempotency_key = %s, updated_at = now() "  # noqa: E501
                "where tenant_id = %s and id = %s",
                (
                    payload.order_number,
                    payload.supplier_id,
                    payload.order_date.isoformat(),
                    payload.expected_delivery_date.isoformat()
                    if payload.expected_delivery_date
                    else None,
                    _decimal(payload.total.amount),
                    payload.total.currency,
                    _decimal(payload.tax.amount),
                    payload.tax.currency,
                    payload.source_kind,
                    payload.source_reference,
                    payload.source_hash,
                    payload.source_request_id,
                    idempotency_key,
                    member.tenant_id,
                    order_id,
                ),
            )

            cur.execute(
                "delete from purchase_order_line where tenant_id = %s and purchase_order_id = %s",
                (member.tenant_id, order_id),
            )

            cur.executemany(
                "insert into purchase_order_line (tenant_id,purchase_order_id,line_number,"
                "workspace_product_id,description,ordered_quantity,base_unit,unit_price_amount,"
                "unit_price_currency,tax_amount,tax_currency,line_total_amount,"
                "line_total_currency,source_request_id,source_request_line_id) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        member.tenant_id,
                        order_id,
                        line.line_number,
                        line.workspace_product_id,
                        line.description,
                        line.ordered_quantity,
                        line.base_unit,
                        line.unit_price.amount,
                        line.unit_price.currency,
                        line.tax.amount,
                        line.tax.currency,
                        line.line_total.amount,
                        line.line_total.currency,
                        payload.source_request_id,
                        line.source_request_line_id,
                    )
                    for line in payload.lines
                ],
            )

            order = self._load_order_cursor(cur, order_id)
            self._audit_cursor(cur, member, "orders.purchase_order_edited", order_id)

        return order

    def cancel_order(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        order_id: UUID,
        idempotency_key: UUID,
    ) -> PurchaseOrder:
        self._require_write(member, idempotency_key)

        with self._transaction(member) as cur:
            cur.execute(
                f"select {ORDER_HEADER_COLUMNS} from purchase_order "
                "where tenant_id = %s and id = %s for update",
                (member.tenant_id, order_id),
            )
            row = cur.fetchone()
            if row is None:
                raise NotFoundError(details={"resource": "purchase_order"})

            if row["status"] == "cancelled":
                if row.get("cancel_idempotency_key") and str(row["cancel_idempotency_key"]) == str(
                    idempotency_key
                ):
                    return self._load_order_cursor(cur, order_id)
                raise ConflictError(details={"reason": "order_already_cancelled"})

            if row["status"] in ("received", "closed"):
                raise ConflictError(details={"reason": "order_not_cancellable"})

            if row.get("source_request_id"):
                self._lock_requests(cur, member.tenant_id, {UUID(str(row["source_request_id"]))})

            cur.execute(
                "select 1 from purchase_order where tenant_id = %s "
                "and cancel_idempotency_key = %s and id != %s",
                (member.tenant_id, idempotency_key, order_id),
            )
            if cur.fetchone() is not None:
                raise ConflictError(details={"reason": "order_number_or_idempotency_exists"})

            cur.execute(
                "update purchase_order set status = 'cancelled', cancel_idempotency_key = %s, updated_at = now() "  # noqa: E501
                "where tenant_id = %s and id = %s",
                (idempotency_key, member.tenant_id, order_id),
            )

            order = self._load_order_cursor(cur, order_id)
            self._audit_cursor(cur, member, "orders.purchase_order_cancelled", order_id)

        return order

    def get_request_allocation(
        self, *, bearer_token: str, member: CurrentMember, source_request_id: UUID
    ) -> RequestAllocation:
        from decimal import Decimal

        from procurepilot_api.modules.requests.service import RequestsService

        requests_service = RequestsService(self._settings)
        request = requests_service.get_request(
            bearer_token=bearer_token, member=member, request_id=source_request_id
        )

        req_line_ids = [line.id for line in request.lines]

        with self._transaction(member) as cur:
            cur.execute(
                "select pol.source_request_line_id, sum(case when po.status != 'cancelled' then pol.ordered_quantity "  # noqa: E501
                "else coalesce(receipts.total_received, 0) end) as allocated_quantity "  # noqa: E501
                "from purchase_order_line pol "
                "join purchase_order po on po.tenant_id = pol.tenant_id and po.id = pol.purchase_order_id "  # noqa: E501
                "left join (select tenant_id, purchase_order_line_id, sum(received_quantity) as total_received "  # noqa: E501
                "from delivery_receipt_line where tenant_id = %s group by tenant_id, purchase_order_line_id) receipts "  # noqa: E501
                "on receipts.tenant_id = pol.tenant_id and receipts.purchase_order_line_id = pol.id "  # noqa: E501
                "where po.tenant_id = %s and pol.source_request_line_id = any(%s) "  # noqa: E501
                "group by pol.source_request_line_id",
                (member.tenant_id, member.tenant_id, req_line_ids),
            )
            allocations = {
                str(r["source_request_line_id"]): r["allocated_quantity"] for r in cur.fetchall()
            }

        line_allocations = []
        for line in request.lines:
            allocated = Decimal(str(allocations.get(str(line.id), 0)))
            requested_quantity = Decimal(str(line.quantity))
            remaining = requested_quantity - allocated
            line_allocations.append(
                RequestLineAllocation(
                    source_request_line_id=line.id,
                    requested_quantity=requested_quantity,
                    allocated_quantity=allocated,
                    remaining_quantity=remaining,
                )
            )

        return RequestAllocation(
            source_request_id=source_request_id,
            lines=tuple(line_allocations),
        )

    @staticmethod
    def _lock_requests(cur: psycopg.Cursor, tenant_id: UUID, request_ids: set[UUID]) -> None:
        for req_id in sorted(request_ids):
            lock_id = (tenant_id.int ^ req_id.int) & 0x7FFFFFFFFFFFFFFF
            cur.execute("select pg_advisory_xact_lock(%s)", (lock_id,))

    @staticmethod
    def _assert_request_allocation_available(
        *,
        cur: psycopg.Cursor,
        tenant_id: UUID,
        request_lines_by_id: dict[UUID, object],
        lines: tuple[object, ...],
        excluded_order_id: UUID | None = None,
    ) -> None:
        from collections import defaultdict

        incoming: dict[str, Decimal] = defaultdict(Decimal)
        for line in lines:
            incoming[str(line.source_request_line_id)] += line.ordered_quantity

        if not incoming:
            return

        excluded_clause = ""
        params: tuple[object, ...] = (
            tenant_id,
            tenant_id,
            list(request_lines_by_id.keys()),
        )
        if excluded_order_id is not None:
            excluded_clause = "and pol.purchase_order_id != %s "
            params = (*params, excluded_order_id)

        cur.execute(
            "select pol.source_request_line_id, "
            "sum(case when po.status != 'cancelled' then pol.ordered_quantity "
            "else coalesce(receipts.total_received, 0) end) as allocated "
            "from purchase_order_line pol "
            "join purchase_order po on po.tenant_id = pol.tenant_id "
            "and po.id = pol.purchase_order_id "
            "left join (select tenant_id, purchase_order_line_id, "
            "sum(received_quantity) as total_received "
            "from delivery_receipt_line where tenant_id = %s "
            "group by tenant_id, purchase_order_line_id) receipts "
            "on receipts.tenant_id = pol.tenant_id "
            "and receipts.purchase_order_line_id = pol.id "
            "where po.tenant_id = %s and pol.source_request_line_id = any(%s) "
            f"{excluded_clause}"
            "group by pol.source_request_line_id",
            params,
        )
        allocations = {str(r["source_request_line_id"]): r["allocated"] for r in cur.fetchall()}

        for req_line_id_str, qty in incoming.items():
            req_line = request_lines_by_id[UUID(req_line_id_str)]
            allocated = Decimal(str(allocations.get(req_line_id_str, "0")))
            requested_quantity = Decimal(str(req_line.quantity))
            if qty > (requested_quantity - allocated):
                raise ConflictError(details={"reason": "quantity_exceeds_allocation"})

    def list_orders(
        self, *, bearer_token: str, limit: int = 50, cursor: str | None = None
    ) -> PurchaseOrderList:
        client = authenticated_client(self._settings, bearer_token)
        capped = max(1, min(limit, 100))
        offset = _cursor(cursor)
        try:
            rows = (
                client.table("purchase_order")
                .select(ORDER_HEADER_COLUMNS)
                .order("created_at", desc=True)
                .order("id")
                .range(offset, offset + capped)
                .execute()
            ).data
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        visible = _rows(rows)[:capped]
        orders = tuple(self._load_order(client, UUID(str(row["id"]))) for row in visible)
        return PurchaseOrderList(
            items=orders, next_cursor=str(offset + capped) if len(_rows(rows)) > capped else None
        )

    def get_order(self, *, bearer_token: str, order_id: UUID) -> OrderEvidenceProjection:
        client = authenticated_client(self._settings, bearer_token)
        return self._evidence(client, order_id)

    def submit_order(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        order_id: UUID,
        idempotency_key: UUID | None,
    ) -> PurchaseOrder:
        self._require_write(member, idempotency_key)
        with self._transaction(member) as cur:
            cur.execute(
                f"select {ORDER_HEADER_COLUMNS} from purchase_order "
                "where tenant_id = %s and id = %s for update",
                (member.tenant_id, order_id),
            )
            current = cur.fetchone()
            if current is None:
                raise NotFoundError(details={"resource": "purchase_order"})
            if _submit_action(current, idempotency_key) == "replay":
                return self._load_order_cursor(cur, order_id)
            cur.execute(
                "update purchase_order set status = 'submitted', submit_idempotency_key = %s, "
                "updated_at = now() where tenant_id = %s and id = %s returning "
                f"{ORDER_HEADER_COLUMNS}",
                (idempotency_key, member.tenant_id, order_id),
            )
            updated = cur.fetchone()
            if updated is None:
                raise ConflictError(details={"reason": "order_submit_failed"})
            order = self._load_order_cursor(cur, order_id)
            self._audit_cursor(cur, member, "orders.purchase_order_submitted", order_id)
        return order

    def record_confirmation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        order_id: UUID,
        payload: SupplierConfirmationCreate,
        idempotency_key: UUID | None,
    ) -> OrderEvidenceProjection:
        self._require_write(member, idempotency_key)
        client = authenticated_client(self._settings, bearer_token)
        order = self._load_order(client, order_id)
        try:
            confirmation = SupplierConfirmation(
                id=UUID(int=0),
                tenant_id=member.tenant_id,
                purchase_order_id=order.id,
                supplier_reference=payload.supplier_reference,
                confirmed_at=payload.confirmed_at,
                expected_delivery_date=payload.expected_delivery_date,
                source_kind=payload.source_kind,
                source_reference=payload.source_reference,
                source_hash=payload.source_hash,
                recorded_by=member.membership_id,
                created_at=datetime.now(UTC),
                lines=tuple(
                    SupplierConfirmationLine(id=UUID(int=0), **line.model_dump())
                    for line in payload.lines
                ),
            )
            validate_confirmation_against_order(order, confirmation)
        except ValueError as exc:
            raise UnprocessableEntityError(details={"reason": "invalid_confirmation"}) from exc
        with self._transaction(member) as cur:
            cur.execute(
                "insert into supplier_confirmation (tenant_id,purchase_order_id,supplier_reference,"
                "confirmed_at,expected_delivery_date,source_kind,source_reference,source_hash,"
                "recorded_by,idempotency_key) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing returning "
                f"{CONFIRMATION_COLUMNS}",
                (
                    member.tenant_id,
                    order_id,
                    payload.supplier_reference,
                    payload.confirmed_at,
                    payload.expected_delivery_date,
                    payload.source_kind,
                    payload.source_reference,
                    payload.source_hash,
                    member.membership_id,
                    idempotency_key,
                ),
            )
            row = cur.fetchone()
            created = row is not None
            if row is None:
                cur.execute(
                    f"select {CONFIRMATION_COLUMNS},purchase_order_id from supplier_confirmation "
                    "where tenant_id = %s and idempotency_key = %s for update",
                    (member.tenant_id, idempotency_key),
                )
                row = cur.fetchone()
                if row is None:
                    raise ConflictError(details={"reason": "confirmation_idempotency_conflict"})
                _assert_same_order(row, order_id)
            confirmation_id = UUID(str(row["id"]))
            if created:
                cur.executemany(
                    "insert into supplier_confirmation_line (tenant_id,supplier_confirmation_id,"
                    "purchase_order_id,purchase_order_line_id,confirmed_quantity,"
                    "confirmed_unit_price_amount,confirmed_unit_price_currency) "
                    "values (%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            member.tenant_id,
                            confirmation_id,
                            order_id,
                            line.purchase_order_line_id,
                            line.confirmed_quantity,
                            line.confirmed_unit_price.amount if line.confirmed_unit_price else None,
                            line.confirmed_unit_price.currency
                            if line.confirmed_unit_price
                            else None,
                        )
                        for line in payload.lines
                    ],
                )
                self._audit_cursor(
                    cur, member, "orders.supplier_confirmation_recorded", confirmation_id
                )
            confirmation = self._load_confirmation_cursor(cur, confirmation_id)
        return self._evidence(client, order_id)

    def record_receipt(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        order_id: UUID,
        payload: DeliveryReceiptCreate,
        idempotency_key: UUID | None,
    ) -> OrderEvidenceProjection:
        self._require_write(member, idempotency_key)
        client = authenticated_client(self._settings, bearer_token)
        order = self._load_order(client, order_id)
        try:
            receipt = DeliveryReceipt(
                id=UUID(int=0),
                tenant_id=member.tenant_id,
                purchase_order_id=order.id,
                receipt_reference=payload.receipt_reference,
                receipt_date=payload.receipt_date,
                received_by=member.membership_id,
                source_kind=payload.source_kind,
                source_reference=payload.source_reference,
                source_hash=payload.source_hash,
                created_at=datetime.now(UTC),
                lines=tuple(
                    DeliveryReceiptLine(id=UUID(int=0), **line.model_dump())
                    for line in payload.lines
                ),
            )
            validate_receipt_against_order(order, receipt)
        except ValueError as exc:
            raise UnprocessableEntityError(details={"reason": "invalid_receipt"}) from exc
        with self._transaction(member) as cur:
            cur.execute(
                "insert into delivery_receipt (tenant_id,purchase_order_id,receipt_reference,"
                "receipt_date,"
                "received_by,source_kind,source_reference,source_hash,idempotency_key) values "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing returning "
                f"{RECEIPT_COLUMNS}",
                (
                    member.tenant_id,
                    order_id,
                    payload.receipt_reference,
                    payload.receipt_date,
                    member.membership_id,
                    payload.source_kind,
                    payload.source_reference,
                    payload.source_hash,
                    idempotency_key,
                ),
            )
            row = cur.fetchone()
            created = row is not None
            if row is None:
                cur.execute(
                    f"select {RECEIPT_COLUMNS} from delivery_receipt "
                    "where tenant_id = %s and idempotency_key = %s for update",
                    (member.tenant_id, idempotency_key),
                )
                row = cur.fetchone()
                if row is None:
                    raise ConflictError(details={"reason": "receipt_idempotency_conflict"})
                _assert_same_order(row, order_id)
            receipt_id = UUID(str(row["id"]))
            if created:
                cur.executemany(
                    "insert into delivery_receipt_line (tenant_id,delivery_receipt_id,"
                    "purchase_order_id,"
                    "purchase_order_line_id,received_quantity) values (%s,%s,%s,%s,%s)",
                    [
                        (
                            member.tenant_id,
                            receipt_id,
                            order_id,
                            line.purchase_order_line_id,
                            line.received_quantity,
                        )
                        for line in payload.lines
                    ],
                )
                self._audit_cursor(cur, member, "orders.delivery_receipt_recorded", receipt_id)
            receipt = self._load_receipt_cursor(cur, receipt_id)
        return self._evidence(client, order_id)

    def _evidence(self, client: Client, order_id: UUID) -> OrderEvidenceProjection:
        order = self._load_order(client, order_id)
        confirmations = tuple(self._load_confirmations(client, order_id))
        receipts = tuple(self._load_receipts(client, order_id))
        lifecycle = build_lifecycle_summary(order, confirmations, receipts)
        latest_confirmation = max(
            confirmations, key=lambda item: (item.confirmed_at, item.id), default=None
        )
        return OrderEvidenceProjection(
            order=order,
            confirmation=latest_confirmation,
            receipts=receipts,
            lifecycle=lifecycle,
        )

    @contextmanager
    def _transaction(self, member: CurrentMember) -> Iterator[psycopg.Cursor]:
        claims = json.dumps(
            {
                "sub": str(member.user_id),
                "tenant_id": str(member.tenant_id),
                "role": "authenticated",
                "member_role": member.role.value,
            }
        )
        try:
            with psycopg.connect(
                self._settings.database_url.get_secret_value(),
                row_factory=dict_row,
                # Supabase's transaction pooler does not preserve prepared statements.
                prepare_threshold=None,
            ) as conn:
                with conn.transaction():
                    conn.execute("set local role authenticated")
                    conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
                    with conn.cursor() as cur:
                        yield cur
        except (ConflictError, NotFoundError, UnprocessableEntityError):
            raise
        except psycopg.Error as exc:
            raise _database_error(exc) from exc

    @staticmethod
    def _audit_cursor(
        cur: psycopg.Cursor, member: CurrentMember, action: str, identifier: UUID
    ) -> None:
        cur.execute(
            "select record_audit_event(%s, %s::audit_outcome, %s, %s, %s, %s::jsonb, null)",
            (
                action,
                "success",
                member.tenant_id,
                member.membership_id,
                member.email,
                json.dumps({"id": str(identifier)}),
            ),
        )

    @staticmethod
    def _load_order_cursor(cur: psycopg.Cursor, order_id: UUID) -> PurchaseOrder:
        cur.execute(f"select {ORDER_HEADER_COLUMNS} from purchase_order where id = %s", (order_id,))
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "purchase_order"})
        cur.execute(
            f"select {ORDER_LINE_COLUMNS} from purchase_order_line "
            "where purchase_order_id = %s order by line_number",
            (order_id,),
        )
        return _order_model(row, cur.fetchall())

    @staticmethod
    def _load_confirmation_cursor(cur: psycopg.Cursor, identifier: UUID) -> SupplierConfirmation:
        cur.execute(
            f"select {CONFIRMATION_COLUMNS} from supplier_confirmation where id = %s", (identifier,)
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "supplier_confirmation"})
        cur.execute(
            f"select {CONFIRMATION_LINE_COLUMNS} from supplier_confirmation_line "
            "where supplier_confirmation_id = %s",
            (identifier,),
        )
        return _confirmation_model(row, cur.fetchall())

    @staticmethod
    def _load_receipt_cursor(cur: psycopg.Cursor, identifier: UUID) -> DeliveryReceipt:
        cur.execute(f"select {RECEIPT_COLUMNS} from delivery_receipt where id = %s", (identifier,))
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "delivery_receipt"})
        cur.execute(
            f"select {RECEIPT_LINE_COLUMNS} from delivery_receipt_line "
            "where delivery_receipt_id = %s",
            (identifier,),
        )
        return _receipt_model(row, cur.fetchall())

    def _load_order(self, client: Client, order_id: UUID) -> PurchaseOrder:
        response = (
            client.table("purchase_order")
            .select(ORDER_HEADER_COLUMNS)
            .eq("id", str(order_id))
            .limit(2)
            .execute()
        )
        row = _not_found(response.data, "purchase_order")
        lines = _rows(
            client.table("purchase_order_line")
            .select(ORDER_LINE_COLUMNS)
            .eq("purchase_order_id", str(order_id))
            .order("line_number")
            .execute()
            .data
        )
        return _order_model(row, lines)

    def _load_confirmations(self, client: Client, order_id: UUID) -> list[SupplierConfirmation]:
        rows = _rows(
            client.table("supplier_confirmation")
            .select(CONFIRMATION_COLUMNS)
            .eq("purchase_order_id", str(order_id))
            .order("confirmed_at")
            .execute()
            .data
        )
        result = []
        for row in rows:
            lines = _rows(
                client.table("supplier_confirmation_line")
                .select(CONFIRMATION_LINE_COLUMNS)
                .eq("supplier_confirmation_id", str(row["id"]))
                .execute()
                .data
            )
            result.append(_confirmation_model(row, lines))
        return result

    def _load_receipts(self, client: Client, order_id: UUID) -> list[DeliveryReceipt]:
        rows = _rows(
            client.table("delivery_receipt")
            .select(RECEIPT_COLUMNS)
            .eq("purchase_order_id", str(order_id))
            .order("receipt_date")
            .execute()
            .data
        )
        result = []
        for row in rows:
            lines = _rows(
                client.table("delivery_receipt_line")
                .select(RECEIPT_LINE_COLUMNS)
                .eq("delivery_receipt_id", str(row["id"]))
                .execute()
                .data
            )
            result.append(_receipt_model(row, lines))
        return result

    def _by_idempotency(self, client: Client, table: str, key: UUID) -> dict[str, object]:
        return _not_found(
            client.table(table)
            .select(ORDER_COLUMNS)
            .eq("idempotency_key", str(key))
            .limit(2)
            .execute()
            .data,
            table,
        )

    @staticmethod
    def _confirmation_lines_exist(client: Client, identifier: UUID) -> bool:
        return bool(
            _rows(
                client.table("supplier_confirmation_line")
                .select("id")
                .eq("supplier_confirmation_id", str(identifier))
                .limit(1)
                .execute()
                .data
            )
        )

    @staticmethod
    def _receipt_lines_exist(client: Client, identifier: UUID) -> bool:
        return bool(
            _rows(
                client.table("delivery_receipt_line")
                .select("id")
                .eq("delivery_receipt_id", str(identifier))
                .limit(1)
                .execute()
                .data
            )
        )

    @staticmethod
    def _require_write(member: CurrentMember, idempotency_key: UUID | None) -> None:
        if member.role not in WRITE_ROLES:
            raise PermissionDeniedError(details={"required_roles": ["owner", "buyer"]})
        if idempotency_key is None:
            raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})

    @staticmethod
    def _audit(token: str, member: CurrentMember, action: str, identifier: UUID) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                outcome="success",
                target={"id": str(identifier)},
            ),
            bearer_token=token,
        )


def _decimal(value: Decimal | object) -> str:
    return str(value)


def _money_payload(amount: object, currency: object) -> dict[str, object]:
    value = Decimal(str(amount))
    normalized = format(value.normalize(), "f")
    if "." not in normalized:
        normalized = f"{normalized}.00"
    whole, fraction = normalized.split(".", 1)
    if len(fraction) == 1:
        normalized = f"{whole}.{fraction}0"
    return {"amount": normalized, "currency": currency}


def _submit_action(row: dict[str, object], key: UUID) -> str:
    if str(row.get("submit_idempotency_key")) == str(key):
        return "replay"
    if row["status"] != "draft":
        raise ConflictError(details={"reason": "order_not_draft"})
    return "submit"


def _assert_same_order(row: dict[str, object], order_id: UUID) -> None:
    if UUID(str(row["purchase_order_id"])) != order_id:
        raise ConflictError(details={"reason": "idempotency_key_used_for_another_order"})


def _order_model(
    row: dict[str, object], lines: list[dict[str, object]] | tuple[dict[str, object], ...]
) -> PurchaseOrder:
    return _model(
        PurchaseOrder,
        {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "order_number": row["order_number"],
            "supplier_id": row["supplier_id"],
            "status": row["status"],
            "order_date": row["order_date"],
            "expected_delivery_date": row["expected_delivery_date"],
            "total": _money_payload(row["total_amount"], row["total_currency"]),
            "tax": _money_payload(row["tax_amount"], row["tax_currency"]),
            "source_kind": row["source_kind"],
            "source_reference": row["source_reference"],
            "source_hash": row["source_hash"],
            "source_request_id": row.get("source_request_id"),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "lines": [_order_line_model(line) for line in lines],
        },
    )


def _order_line_model(row: dict[str, object]) -> PurchaseOrderLine:
    return _model(
        PurchaseOrderLine,
        {
            "id": row["id"],
            "line_number": row["line_number"],
            "workspace_product_id": row["workspace_product_id"],
            "description": row["description"],
            "ordered_quantity": row["ordered_quantity"],
            "base_unit": row["base_unit"],
            "unit_price": _money_payload(row["unit_price_amount"], row["unit_price_currency"]),
            "tax": _money_payload(row["tax_amount"], row["tax_currency"]),
            "source_request_line_id": row.get("source_request_line_id"),
            "line_total": _money_payload(row["line_total_amount"], row["line_total_currency"]),
        },
    )


def _confirmation_model(
    row: dict[str, object], lines: list[dict[str, object]] | tuple[dict[str, object], ...]
) -> SupplierConfirmation:
    return _model(
        SupplierConfirmation,
        {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "purchase_order_id": row["purchase_order_id"],
            "supplier_reference": row["supplier_reference"],
            "confirmed_at": row["confirmed_at"],
            "expected_delivery_date": row["expected_delivery_date"],
            "source_kind": row["source_kind"],
            "source_reference": row["source_reference"],
            "source_hash": row["source_hash"],
            "recorded_by": row["recorded_by"],
            "created_at": row["created_at"],
            "lines": [_confirmation_line_model(line) for line in lines],
        },
    )


def _confirmation_line_model(row: dict[str, object]) -> SupplierConfirmationLine:
    amount = row["confirmed_unit_price_amount"]
    return _model(
        SupplierConfirmationLine,
        {
            "id": row["id"],
            "purchase_order_line_id": row["purchase_order_line_id"],
            "confirmed_quantity": row["confirmed_quantity"],
            "confirmed_unit_price": (
                _money_payload(amount, row["confirmed_unit_price_currency"])
                if amount is not None
                else None
            ),
        },
    )


def _receipt_model(
    row: dict[str, object], lines: list[dict[str, object]] | tuple[dict[str, object], ...]
) -> DeliveryReceipt:
    return _model(
        DeliveryReceipt,
        {
            "id": row["id"],
            "tenant_id": row["tenant_id"],
            "purchase_order_id": row["purchase_order_id"],
            "receipt_reference": row["receipt_reference"],
            "receipt_date": row["receipt_date"],
            "received_by": row["received_by"],
            "source_kind": row["source_kind"],
            "source_reference": row["source_reference"],
            "source_hash": row["source_hash"],
            "created_at": row["created_at"],
            "lines": [_receipt_line_model(line) for line in lines],
        },
    )


def _receipt_line_model(row: dict[str, object]) -> DeliveryReceiptLine:
    return _model(
        DeliveryReceiptLine,
        {
            "id": row["id"],
            "purchase_order_line_id": row["purchase_order_line_id"],
            "received_quantity": row["received_quantity"],
        },
    )


def _model[ModelT: BaseModel](model: type[ModelT], payload: dict[str, object]) -> ModelT:
    try:
        return model.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise UnprocessableEntityError(details={"reason": "invalid_database_record"}) from exc


def _database_error(
    exc: psycopg.Error,
) -> ConflictError | UnprocessableEntityError | ServiceUnavailableError:
    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    LOGGER.exception("Order tracking database operation failed", extra={"sqlstate": sqlstate})
    if sqlstate in {"23505", "23P01"}:
        return ConflictError(details={"reason": "database_conflict"})
    if (isinstance(sqlstate, str) and sqlstate.startswith("22")) or sqlstate in {
        "23502",
        "23503",
        "23514",
        "42804",
        "42846",
    }:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    return ServiceUnavailableError(details={"dependency": "database"})


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _one(data: object, reason: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": reason})
    return rows[0]


def _not_found(data: object, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if not rows:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": f"{resource}_ambiguous"})
    return rows[0]


def _code(exc: APIError) -> str | None:
    value = getattr(exc, "code", None)
    return str(value) if value else None


def _write_error(
    exc: APIError, duplicate_reason: str
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    if _code(exc) in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    if _code(exc) == "23505":
        return ConflictError(details={"reason": duplicate_reason})
    return ServiceUnavailableError(details={"dependency": "database"})


def _cursor(value: str | None) -> int:
    if value is None:
        return 0
    try:
        result = int(value)
    except ValueError as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if result < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return result


def get_orders_service() -> OrdersService:
    return OrdersService()
