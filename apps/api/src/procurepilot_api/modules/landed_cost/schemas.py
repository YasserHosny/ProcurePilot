from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class LandedCost(BaseModel):
    id: UUID
    quotation_line_id: UUID
    match_decision_id: UUID
    quantity: str
    normalised_base_quantity: str
    base_unit: str
    unit_price: Money
    vat_amount: Money
    delivery_fee: Money
    discount: Money
    other_charges: Money
    total: Money
    raw_inputs: dict[str, object]
    rule_version: str
    valid_from: datetime
    valid_to: datetime | None = None
    recorded_at: datetime
    created_at: datetime | None = None
