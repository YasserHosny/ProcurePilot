from __future__ import annotations

import base64
import csv
from datetime import UTC, datetime
from io import StringIO
from typing import Literal
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.documents.schemas import Document
from procurepilot_api.modules.documents.service import DOCUMENT_COLUMNS
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import (
    AuditTrailEntry,
    AuditTrailResponse,
    FieldExtraction,
    Money,
    Pack,
    Quotation,
    QuotationCreate,
    QuotationDetail,
    QuotationLine,
    QuotationVersionReference,
    ReviewTask,
    ReviewTaskList,
    ReviewTaskPriority,
    ReviewTaskStatus,
    decimal_string,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

QUOTATION_COLUMNS = (
    "id,document_id,supplier_id,suggested_supplier_id,supplier_match_confidence,currency,"
    "issue_date,expiry_date,status,previous_quotation_id,stated_total_amount,"
    "stated_total_currency,arithmetic_status,created_at,reviewed_by,reviewed_at,deleted_at,"
    "reviewer_notes"
)
LINE_COLUMNS = (
    "id,line_number,original_text,quantity,pack_count,unit_size,pack_unit,unit_price_amount,"
    "unit_price_currency,vat_rate,delivery_fee_amount,delivery_fee_currency,discount_amount,"
    "discount_currency"
)
FIELD_COLUMNS = (
    "id,quotation_id,entity_type,entity_id,field_name,extracted_value,confidence,source_page,"
    "source_region,extraction_method,model_version,corrected_value,corrected_by,corrected_at"
)
TASK_COLUMNS = (
    "id,quotation_id,status,priority,reason,created_at,resolved_at,"
    "quotation(deleted_at,stated_total_amount,stated_total_currency,"
    "supplier!quotation_supplier_id_fkey(name))"
)


class QuotationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_quotation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: QuotationCreate,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        _document_row(client, payload.document_id)
        if payload.supplier_id is not None:
            _supplier_row(client, payload.supplier_id)
        if _active_or_existing_quotation_for_document(client, payload.document_id):
            raise ConflictError(details={"reason": "document_already_has_quotation"})
        try:
            response = client.table("quotation").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "document_id": str(payload.document_id),
                    "supplier_id": str(payload.supplier_id) if payload.supplier_id else None,
                    "status": "pending",
                }
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _quotation(_one_row(response.data, resource="quotation"))

    def get_quotation(self, *, bearer_token: str, quotation_id: UUID) -> QuotationDetail:
        client = authenticated_client(self._settings, bearer_token)
        quote = _quotation_row(client, quotation_id)
        document = Document.model_validate(_document_row(client, UUID(str(quote["document_id"]))))
        lines = _line_rows(client, quotation_id)
        fields = _field_rows(client, quotation_id)
        task = _open_or_latest_task(client, quotation_id)
        previous = (
            _version_reference(_quotation_row(client, UUID(str(quote["previous_quotation_id"]))))
            if quote.get("previous_quotation_id")
            else None
        )
        next_versions = _next_versions(client, quotation_id)
        uploaded_by_email = (
            _membership_email(client, document.created_by) if document.created_by else None
        )
        reviewed_by_email = (
            _membership_email(client, UUID(str(quote["reviewed_by"])))
            if quote.get("reviewed_by")
            else None
        )
        suggested_supplier_name = (
            _supplier_name(client, UUID(str(quote["suggested_supplier_id"])))
            if quote.get("suggested_supplier_id")
            else None
        )
        return QuotationDetail(
            **_quotation(quote).model_dump(),
            document=document,
            lines=[_line(row) for row in lines],
            field_extractions=[_field(row) for row in fields],
            review_task=_task(task) if task else None,
            previous_version=previous,
            next_versions=next_versions,
            uploaded_by_email=uploaded_by_email,
            reviewed_by_email=reviewed_by_email,
            suggested_supplier_name=suggested_supplier_name,
        )

    def list_review_tasks(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
        status: ReviewTaskStatus | str = "open",
        priority: ReviewTaskPriority | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: Literal["created_at", "stated_total", "priority", "status"] = "created_at",
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> ReviewTaskList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        clean_search = search.strip()[:200].lower() if search else None
        try:
            query = client.table("review_task").select(TASK_COLUMNS)
            if status != "all":
                query = query.eq("status", status)
            if priority is not None:
                query = query.eq("priority", priority)
            if date_from is not None:
                query = query.gte("created_at", date_from)
            if date_to is not None:
                query = query.lte("created_at", date_to)
            response = (
                query.order(sort_by, desc=sort_order == "desc")
                .order("id")
                .range(offset, offset + capped_limit)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        rows = [row for row in rows if not _task_quotation_deleted(row)]
        if clean_search:
            rows = [
                r for r in rows
                if clean_search in str(r.get("quotation_id", "")).lower()
                or clean_search in _nested_supplier_name(r).lower()
            ]
        visible = rows[:capped_limit]
        return ReviewTaskList(
            items=[_task(row) for row in visible],
            next_cursor=(
                _encode_cursor(offset + capped_limit)
                if len(rows) > capped_limit
                else None
            ),
        )

    def get_audit_trail(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> AuditTrailResponse:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("audit_event")
                .select("id,action,actor_email,outcome,target,trace_id,occurred_at")
                .eq("tenant_id", str(member.tenant_id))
                .eq("target->>quotation_id", str(quotation_id))
                .order("occurred_at", desc=True)
                .limit(100)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        items = [AuditTrailEntry.model_validate(row) for row in _rows(response.data)]
        return AuditTrailResponse(items=items)

    def update_review_task_priority(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        task_id: UUID,
        priority: ReviewTaskPriority,
    ) -> ReviewTask:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("review_task")
                .update({"priority": priority})
                .eq("id", str(task_id))
                .select(TASK_COLUMNS)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        row = _one_row(response.data, resource="review_task")
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="review_task.priority_changed",
            target={"review_task_id": str(task_id), "priority": priority},
        )
        return _task(row)

    def archive_quotation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        _quotation_row(client, quotation_id)
        archived_at = datetime.now(UTC).isoformat()
        try:
            row = _one_row(
                client.table("quotation")
                .update({"deleted_at": archived_at})
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
            client.table("review_task").update(
                {"status": "resolved", "resolved_at": archived_at}
            ).eq("quotation_id", str(quotation_id)).in_(
                "status", ["open", "in_progress"]
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.archived",
            target={"quotation_id": str(quotation_id)},
        )
        return _quotation(row)

    def restore_quotation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        _quotation_row(client, quotation_id)
        try:
            row = _one_row(
                client.table("quotation")
                .update({"deleted_at": None})
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.restored",
            target={"quotation_id": str(quotation_id)},
        )
        return _quotation(row)

    def retry_extraction(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        quote = _quotation_row(client, quotation_id)
        if quote["status"] in {"pending", "extracting"}:
            raise ConflictError(details={"reason": "quotation_extraction_already_active"})
        try:
            active = (
                client.table("extraction_job")
                .select("id")
                .eq("quotation_id", str(quotation_id))
                .in_("status", ["queued", "running"])
                .limit(1)
                .execute()
            )
            if active.data:
                raise ConflictError(details={"reason": "extraction_already_running"})
            job_row = _one_row(
                client.table("extraction_job")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_id": str(quotation_id),
                        "status": "queued",
                    }
                )
                .execute()
                .data,
                resource="job",
            )
            row = _one_row(
                client.table("quotation")
                .update({"status": "extracting"})
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        try:
            _enqueue_extraction(self._settings, job_row, quote, member)
        except ServiceUnavailableError:
            _mark_extraction_enqueue_failed(
                client=client,
                job_id=UUID(str(job_row["id"])),
                quotation_id=quotation_id,
                prior_status=str(quote["status"]),
            )
            raise
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.extraction_retried",
            target={"quotation_id": str(quotation_id)},
        )
        return _quotation(row)

    def replace_document(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
        new_document_id: UUID,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        quote = _quotation_row(client, quotation_id)
        if quote["status"] in {"pending", "extracting"}:
            raise ConflictError(details={"reason": "quotation_extraction_already_active"})
        _document_row(client, new_document_id)
        old_document_id = str(quote["document_id"])
        try:
            active = (
                client.table("extraction_job")
                .select("id")
                .eq("quotation_id", str(quotation_id))
                .in_("status", ["queued", "running"])
                .limit(1)
                .execute()
            )
            if active.data:
                raise ConflictError(details={"reason": "extraction_already_running"})
            job_row = _one_row(
                client.table("extraction_job")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_id": str(quotation_id),
                        "status": "queued",
                    }
                )
                .execute()
                .data,
                resource="job",
            )
            row = _one_row(
                client.table("quotation")
                .update({"document_id": str(new_document_id), "status": "extracting"})
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        try:
            _enqueue_extraction(
                self._settings,
                job_row,
                {**quote, "document_id": str(new_document_id)},
                member,
            )
        except ServiceUnavailableError:
            _mark_extraction_enqueue_failed(
                client=client,
                job_id=UUID(str(job_row["id"])),
                quotation_id=quotation_id,
                prior_status=str(quote["status"]),
                document_id=UUID(old_document_id),
            )
            raise
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.document_replaced",
            target={
                "quotation_id": str(quotation_id),
                "old_document_id": old_document_id,
                "new_document_id": str(new_document_id),
            },
        )
        return _quotation(row)

    def export_quotation_csv(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
    ) -> str:
        client = authenticated_client(self._settings, bearer_token)
        quote = _quotation_row(client, quotation_id)
        lines = _line_rows(client, quotation_id)
        supplier_name = (
            _supplier_name(client, UUID(str(quote["supplier_id"])))
            if quote.get("supplier_id")
            else ""
        )

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["supplier_name", supplier_name])
        writer.writerow(["issue_date", quote.get("issue_date") or ""])
        writer.writerow(
            ["stated_total", decimal_string(quote.get("stated_total_amount")) or ""]
        )
        writer.writerow(
            [
                "currency",
                quote.get("stated_total_currency") or quote.get("currency") or "",
            ]
        )
        writer.writerow([])
        writer.writerow(
            [
                "line_number",
                "original_text",
                "quantity",
                "unit_price_amount",
                "unit_price_currency",
                "vat_rate",
                "delivery_fee_amount",
                "discount_amount",
            ]
        )
        for line in lines:
            writer.writerow(
                [
                    line.get("line_number") or "",
                    line.get("original_text") or "",
                    decimal_string(line.get("quantity")) or "",
                    decimal_string(line.get("unit_price_amount")) or "",
                    line.get("unit_price_currency") or "",
                    decimal_string(line.get("vat_rate")) or "",
                    decimal_string(line.get("delivery_fee_amount")) or "",
                    decimal_string(line.get("discount_amount")) or "",
                ]
            )
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.exported",
            target={"quotation_id": str(quotation_id), "format": "csv"},
        )
        return output.getvalue()

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
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )


def get_quotation_service() -> QuotationService:
    return QuotationService()


def _document_row(client: object, document_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("document")
            .select(DOCUMENT_COLUMNS)
            .eq("id", str(document_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="document")


def _quotation_row(client: object, quotation_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("quotation")
            .select(QUOTATION_COLUMNS)
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="quotation")


def _supplier_row(client: object, supplier_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("supplier")
            .select("id")
            .eq("id", str(supplier_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="supplier")


def _supplier_name(client: object, supplier_id: UUID) -> str:
    try:
        response = (
            client.table("supplier")
            .select("name")
            .eq("id", str(supplier_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return str(_one_row(response.data, resource="supplier").get("name") or "")


def _active_or_existing_quotation_for_document(client: object, document_id: UUID) -> bool:
    try:
        rows = _rows(
            client.table("quotation")
            .select("id,status")
            .eq("document_id", str(document_id))
            .limit(1)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return bool(rows)


def _line_rows(client: object, quotation_id: UUID) -> list[dict[str, object]]:
    try:
        response = (
            client.table("quotation_line")
            .select(LINE_COLUMNS)
            .eq("quotation_id", str(quotation_id))
            .order("line_number")
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


def _field_rows(client: object, quotation_id: UUID) -> list[dict[str, object]]:
    try:
        response = (
            client.table("field_extraction")
            .select(FIELD_COLUMNS)
            .eq("quotation_id", str(quotation_id))
            .order("created_at")
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


def _open_or_latest_task(client: object, quotation_id: UUID) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("review_task")
            .select(TASK_COLUMNS)
            .eq("quotation_id", str(quotation_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return rows[0] if rows else None


def _next_versions(client: object, quotation_id: UUID) -> list[QuotationVersionReference]:
    try:
        rows = _rows(
            client.table("quotation")
            .select("id,status,created_at")
            .eq("previous_quotation_id", str(quotation_id))
            .order("created_at")
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return [_version_reference(row) for row in rows]


def _quotation(row: dict[str, object]) -> Quotation:
    return Quotation(
        id=UUID(str(row["id"])),
        document_id=UUID(str(row["document_id"])),
        supplier_id=UUID(str(row["supplier_id"])) if row.get("supplier_id") else None,
        suggested_supplier_id=(
            UUID(str(row["suggested_supplier_id"])) if row.get("suggested_supplier_id") else None
        ),
        supplier_match_confidence=decimal_string(
            row.get("supplier_match_confidence"),
            scale=3,
        ),
        currency=str(row["currency"]) if row.get("currency") else None,
        issue_date=row.get("issue_date"),
        expiry_date=row.get("expiry_date"),
        status=row["status"],
        previous_quotation_id=(
            UUID(str(row["previous_quotation_id"])) if row.get("previous_quotation_id") else None
        ),
        stated_total=_money(row, "stated_total"),
        arithmetic_status=row.get("arithmetic_status"),
        created_at=row["created_at"],
        reviewed_by=UUID(str(row["reviewed_by"])) if row.get("reviewed_by") else None,
        reviewed_at=row.get("reviewed_at"),
        deleted_at=row.get("deleted_at"),
        reviewer_notes=row.get("reviewer_notes"),
    )


def _line(row: dict[str, object]) -> QuotationLine:
    pack = None
    if row.get("pack_count") is not None and row.get("unit_size") is not None:
        pack = Pack(
            pack_count=int(row["pack_count"]),
            unit_size=decimal_string(row["unit_size"]) or "",
            unit=str(row["pack_unit"]) if row.get("pack_unit") else None,
        )
    return QuotationLine(
        id=UUID(str(row["id"])),
        line_number=int(row["line_number"]),
        original_text=str(row["original_text"]),
        quantity=decimal_string(row.get("quantity")),
        pack=pack,
        unit_price=_money(row, "unit_price"),
        vat_rate=decimal_string(row.get("vat_rate")),
        delivery_fee=_money(row, "delivery_fee"),
        discount=_money(row, "discount"),
    )


def _field(row: dict[str, object]) -> FieldExtraction:
    return FieldExtraction(
        id=UUID(str(row["id"])),
        quotation_id=UUID(str(row["quotation_id"])),
        entity_type=row["entity_type"],
        entity_id=UUID(str(row["entity_id"])),
        field_name=str(row["field_name"]),
        extracted_value=row["extracted_value"],
        confidence=decimal_string(row["confidence"], scale=4) or "0.0000",
        source_page=int(row["source_page"]) if row.get("source_page") is not None else None,
        source_region=row.get("source_region"),
        extraction_method=row["extraction_method"],
        model_version=str(row["model_version"]),
        corrected_value=row.get("corrected_value"),
        corrected_by=UUID(str(row["corrected_by"])) if row.get("corrected_by") else None,
        corrected_at=row.get("corrected_at"),
    )


def _nested_supplier_name(row: dict[str, object]) -> str:
    q = row.get("quotation")
    if isinstance(q, dict):
        s = q.get("supplier")
        if isinstance(s, dict):
            return str(s.get("name", ""))
    return ""


def _task_quotation_deleted(row: dict[str, object]) -> bool:
    q = row.get("quotation")
    return isinstance(q, dict) and q.get("deleted_at") is not None


def _task(row: dict[str, object]) -> ReviewTask:
    quotation_data = row.pop("quotation", None)
    supplier_name: str | None = None
    stated_total: Money | None = None
    if isinstance(quotation_data, dict):
        supplier_obj = quotation_data.get("supplier")
        if isinstance(supplier_obj, dict):
            supplier_name = supplier_obj.get("name")
        stated_total = _money(quotation_data, "stated_total")
    task = ReviewTask.model_validate(row)
    task.supplier_name = supplier_name
    task.stated_total = stated_total
    return task


def _version_reference(row: dict[str, object]) -> QuotationVersionReference:
    return QuotationVersionReference.model_validate(row)


def _money(row: dict[str, object], prefix: str) -> Money | None:
    amount = row.get(f"{prefix}_amount")
    currency = row.get(f"{prefix}_currency")
    if amount is None or currency is None:
        return None
    return Money(amount=decimal_string(amount, scale=4) or "0.0000", currency=str(currency))


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"reason": "invalid_database_response"})


def _one_row(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise NotFoundError(details={"resource": resource})
    raise ServiceUnavailableError(details={"reason": "multiple_rows", "resource": resource})


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise NotFoundError(details={"cursor": "invalid"}) from exc


def _membership_email(client: object, membership_id: UUID) -> str | None:
    try:
        response = (
            client.table("membership")
            .select("email")
            .eq("id", str(membership_id))
            .limit(1)
            .execute()
        )
    except APIError:
        return None
    rows = response.data if isinstance(response.data, list) else []
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("email") or "")
    return None


def _enqueue_extraction(
    settings: Settings,
    job_row: dict[str, object],
    quote: dict[str, object],
    member: CurrentMember,
) -> None:
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise ServiceUnavailableError(details={"dependency": "rq"}) from exc
    try:
        queue = Queue(settings.extraction_queue_name, connection=Redis.from_url(settings.redis_url))
        queue.enqueue(
            "procurepilot_extraction_worker.worker.process_extraction_job",
            {
                "job_id": str(job_row["id"]),
                "tenant_id": str(member.tenant_id),
                "quotation_id": str(quote["id"]),
                "document_id": str(quote["document_id"]),
            },
            job_id=str(job_row["id"]),
        )
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc


def _mark_extraction_enqueue_failed(
    *,
    client: object,
    job_id: UUID,
    quotation_id: UUID,
    prior_status: str,
    document_id: UUID | None = None,
) -> None:
    updates: dict[str, object] = {"status": prior_status}
    if document_id is not None:
        updates["document_id"] = str(document_id)
    try:
        client.table("extraction_job").update(
            {
                "status": "failed",
                "error": {
                    "code": "redis_enqueue_failed",
                    "message": "Extraction job could not be queued in Redis.",
                },
                "completed_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", str(job_id)).execute()
        client.table("quotation").update(updates).eq("id", str(quotation_id)).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
