from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from procurepilot_api.modules.documents.schemas import Document

QuotationStatus = Literal["pending", "extracting", "extracted", "in_review", "reviewed", "refused"]
ArithmeticStatus = Literal["not_applicable", "reconciled", "mismatch"]
ExtractionMethod = Literal["structured_parse", "bedrock", "azure_di"]
EntityType = Literal["quotation", "quotation_line"]
ReviewTaskStatus = Literal["open", "in_progress", "resolved"]
ReviewTaskPriority = Literal["low", "normal", "high"]
ReviewTaskReason = Literal[
    "low_confidence",
    "arithmetic_mismatch",
    "read_failure",
    "review_required",
]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class QuotationCreate(StrictApiModel):
    document_id: UUID
    supplier_id: UUID | None = None


class ConfirmRequest(StrictApiModel):
    previous_quotation_id: UUID | None = None
    acknowledge_mismatch: bool = False


class RefuseRequest(StrictApiModel):
    reason: str | None = None


class Pack(BaseModel):
    pack_count: int = Field(ge=1)
    unit_size: str
    unit: str | None = None


class QuotationLine(BaseModel):
    id: UUID
    line_number: int = Field(ge=1)
    original_text: str
    quantity: str | None = None
    pack: Pack | None = None
    unit_price: Money | None = None
    vat_rate: str | None = None
    delivery_fee: Money | None = None
    discount: Money | None = None


class FieldExtraction(BaseModel):
    id: UUID
    quotation_id: UUID
    entity_type: EntityType
    entity_id: UUID
    field_name: str
    extracted_value: Any
    confidence: str
    source_page: int | None = None
    source_region: dict[str, Any] | None = None
    extraction_method: ExtractionMethod
    model_version: str
    corrected_value: Any | None = None
    corrected_by: UUID | None = None
    corrected_at: datetime | None = None


class FieldCorrection(StrictApiModel):
    field_extraction_id: UUID
    corrected_value: Any


class QuotationReviewPatch(StrictApiModel):
    supplier_id: UUID | None = None
    corrections: list[FieldCorrection] = Field(default_factory=list)


class ReviewTask(BaseModel):
    id: UUID
    quotation_id: UUID
    status: ReviewTaskStatus
    priority: ReviewTaskPriority
    reason: ReviewTaskReason
    created_at: datetime
    resolved_at: datetime | None = None
    supplier_name: str | None = None
    stated_total: Money | None = None


class ReviewTaskList(BaseModel):
    items: list[ReviewTask]
    next_cursor: str | None = None


class Quotation(BaseModel):
    id: UUID
    document_id: UUID
    supplier_id: UUID | None = None
    currency: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    status: QuotationStatus
    previous_quotation_id: UUID | None = None
    stated_total: Money | None = None
    arithmetic_status: ArithmeticStatus | None = None
    created_at: datetime
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None


class QuotationVersionReference(BaseModel):
    id: UUID
    status: QuotationStatus
    created_at: datetime


class QuotationDetail(Quotation):
    document: Document
    lines: list[QuotationLine]
    field_extractions: list[FieldExtraction]
    review_task: ReviewTask | None = None
    previous_version: QuotationVersionReference | None = None
    next_versions: list[QuotationVersionReference] = Field(default_factory=list)


def decimal_string(value: object, *, scale: int | None = None) -> str | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    if scale is not None:
        decimal = decimal.quantize(Decimal(10) ** -scale)
    return format(decimal, "f")
