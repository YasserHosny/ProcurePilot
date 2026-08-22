from __future__ import annotations

import base64
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.documents.schemas import Document
from procurepilot_api.modules.documents.service import DOCUMENT_COLUMNS
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import (
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

QUOTATION_COLUMNS = (
    "id,document_id,supplier_id,currency,issue_date,expiry_date,status,previous_quotation_id,"
    "stated_total_amount,stated_total_currency,arithmetic_status,created_at,reviewed_by,reviewed_at"
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
TASK_COLUMNS = "id,quotation_id,status,priority,reason,created_at,resolved_at"


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
        return QuotationDetail(
            **_quotation(quote).model_dump(),
            document=document,
            lines=[_line(row) for row in lines],
            field_extractions=[_field(row) for row in fields],
            review_task=_task(task) if task else None,
            previous_version=previous,
            next_versions=next_versions,
        )

    def list_review_tasks(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
        status: ReviewTaskStatus | str = "open",
        priority: ReviewTaskPriority | None = None,
    ) -> ReviewTaskList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        try:
            query = client.table("review_task").select(TASK_COLUMNS)
            if status != "all":
                query = query.eq("status", status)
            if priority is not None:
                query = query.eq("priority", priority)
            response = query.order("created_at").order("id").range(
                offset, offset + capped_limit
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        visible = rows[:capped_limit]
        return ReviewTaskList(
            items=[_task(row) for row in visible],
            next_cursor=_encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None,
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


def _task(row: dict[str, object]) -> ReviewTask:
    return ReviewTask.model_validate(row)


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
