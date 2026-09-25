from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RfqStatus = Literal["draft", "sent", "responded", "expired", "converted"]
RfqRecipientStatus = Literal["draft", "sent", "failed"]


class Rfq(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_by_membership_id: UUID
    status: RfqStatus
    needed_by_date: date
    idempotency_key: UUID
    created_at: datetime


class RfqLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    rfq_id: UUID
    workspace_product_id: UUID
    quantity: Decimal
    created_at: datetime


class RfqRecipient(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    rfq_id: UUID
    supplier_id: UUID
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
    quoted_quantity: Decimal
    quoted_unit_price_amount: Decimal
    quoted_unit_price_currency: str
    pending_match: bool


class RfqResponseComparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rfq_id: UUID
    supplier_id: UUID
    submitted_at: datetime
    lines: list[RfqResponseLineComparison]


class RfqResponseComparisonList(BaseModel):
    items: list[RfqResponseComparison]


class PrepareRequestInput(BaseModel):
    rfq_response_id: UUID
    branch_id: UUID
    cost_centre_id: UUID | None = None
    required_by_date: date


class PrepareRequestResponse(BaseModel):
    purchase_request_id: UUID

class GuardrailCreateInput(BaseModel):
    max_order_value_amount: Decimal
    max_order_value_currency: str
    supplier_allowlist: list[UUID] | None = None
    category_allowlist: list[str] | None = None
    min_response_count: int = 1
    max_price_variance_pct: Decimal
    default_branch_id: UUID
    enabled: bool = True

class GuardrailUpdateInput(BaseModel):
    max_order_value_amount: Decimal | None = None
    max_order_value_currency: str | None = None
    supplier_allowlist: list[UUID] | None = None
    category_allowlist: list[str] | None = None
    min_response_count: int | None = None
    max_price_variance_pct: Decimal | None = None
    default_branch_id: UUID | None = None
    enabled: bool | None = None
