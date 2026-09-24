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
    created_at: datetime


class AutoPreparationEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    guardrail_id: UUID
    rfq_response_id: UUID
    purchase_request_id: UUID | None = None
    created_at: datetime
