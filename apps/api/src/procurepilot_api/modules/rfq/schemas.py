import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from procurepilot_api.modules.quotations.schemas import QuotationStatus

RfqStatus = Literal["draft", "sent", "responded", "expired", "converted"]
RfqRecipientStatus = Literal["draft", "sent", "failed"]


class Rfq(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_by_membership_id: UUID
    status: RfqStatus
    needed_by_date: date
    tenant_terms: str | None = None
    idempotency_key: UUID
    created_at: datetime


class RfqLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    rfq_id: UUID
    workspace_product_id: UUID
    quantity: Decimal
    position: int
    product_name: str | None = None
    product_variant: str | None = None
    created_at: datetime


class RfqRecipient(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    rfq_id: UUID
    supplier_id: UUID
    supplier_name: str | None = None
    supplier_contact_email: str | None = None
    status: RfqRecipientStatus
    outbound_message_id: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class RfqResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    rfq_recipient_id: UUID
    quotation_id: UUID
    created_at: datetime


class AutoPreparationGuardrail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_by_membership_id: UUID
    max_order_value_amount: Decimal
    max_order_value_currency: str
    supplier_allowlist: list[UUID] | None = None
    category_allowlist: list[str] | None = None
    min_response_count: int
    max_price_variance_pct: Decimal
    enabled: bool
    default_branch_id: UUID
    default_cost_centre_id: UUID | None = None
    created_at: datetime


class AutoPreparationEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    guardrail_id: UUID
    rfq_response_id: UUID
    purchase_request_id: UUID | None = None
    created_at: datetime


class RfqResponseLineComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_product_id: UUID | None
    original_text: str
    quoted_quantity: Decimal
    quoted_unit_price_amount: Decimal
    quoted_unit_price_currency: str
    pending_match: bool


class RfqGuardrailEvaluation(BaseModel):
    guardrail_id: UUID
    fired: bool
    reason: str
    purchase_request_id: UUID | None = None


class RfqResponseComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rfq_id: UUID
    supplier_id: UUID
    quotation_id: UUID
    submitted_at: datetime
    quotation_status: QuotationStatus
    lines: list[RfqResponseLineComparison]
    guardrail_evaluations: list[RfqGuardrailEvaluation] = Field(default_factory=list)


class RfqResponseComparisonList(BaseModel):
    items: list[RfqResponseComparison]


class RfqPrepareRequestInput(BaseModel):
    rfq_response_id: UUID
    branch_id: UUID
    cost_centre_id: UUID | None = None
    required_by_date: date


class RfqPrepareRequestResponse(BaseModel):
    purchase_request_id: UUID
    status: str = "draft"


class GuardrailCreateInput(BaseModel):
    max_order_value_amount: Decimal
    max_order_value_currency: str
    supplier_allowlist: list[UUID] | None = None
    category_allowlist: list[str] | None = None
    min_response_count: int = 1
    max_price_variance_pct: Decimal
    default_branch_id: UUID
    default_cost_centre_id: UUID | None = None
    enabled: bool = True

    @field_validator("max_order_value_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        if re.fullmatch(r"[A-Z]{3}", value) is None:
            raise ValueError("Currency must be exactly three uppercase letters")
        return value


class GuardrailUpdateInput(BaseModel):
    max_order_value_amount: Decimal | None = None
    max_order_value_currency: str | None = None
    supplier_allowlist: list[UUID] | None = None
    category_allowlist: list[str] | None = None
    min_response_count: int | None = None
    max_price_variance_pct: Decimal | None = None
    default_branch_id: UUID | None = None
    default_cost_centre_id: UUID | None = None
    enabled: bool | None = None

    @field_validator("max_order_value_currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[A-Z]{3}", value) is None:
            raise ValueError("Currency must be exactly three uppercase letters")
        return value


class RfqSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: RfqStatus
    needed_by_date: date
    created_at: datetime
    sent_at: datetime | None = None
    created_by_membership_id: UUID
    recipient_count: int
    response_count: int
    converted_purchase_request_ids: list[UUID] = Field(default_factory=list)
    request_group_id: UUID | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def converted_purchase_request_id(self) -> UUID | None:
        """The first converted request, kept for clients that predate splits (spec 024)."""
        return (
            self.converted_purchase_request_ids[0] if self.converted_purchase_request_ids else None
        )


class RfqList(BaseModel):
    items: list[RfqSummary]
    next_cursor: str | None = None


class RfqDetail(BaseModel):
    converted_purchase_request_ids: list[UUID] = Field(default_factory=list)
    request_group_id: UUID | None = None
    rfq: Rfq
    lines: list[RfqLine]
    recipients: list[RfqRecipient]
