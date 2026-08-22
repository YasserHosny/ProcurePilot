from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MoneyAmount = Decimal


class Money(BaseModel):
    amount: MoneyAmount
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, value: object) -> Decimal:
        return Decimal(str(value))


class PurchaseOutcomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_product_id: UUID
    supplier_id: UUID | None = None
    quotation_line_id: UUID | None = None
    match_decision_id: UUID | None = None
    landed_cost_id: UUID | None = None
    quantity: Decimal = Field(gt=0, decimal_places=6)
    base_unit: str
    unit_price: Money
    total_paid: Money
    delivery_result: Literal["ordered", "partially_delivered", "delivered", "cancelled", "disputed"]
    ordered_at: datetime | None = None
    delivered_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PurchaseRecord(BaseModel):
    id: UUID
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    quotation_line_id: UUID | None = None
    match_decision_id: UUID | None = None
    landed_cost_id: UUID | None = None
    quantity: Decimal
    base_unit: str
    unit_price: Money
    total_paid: Money
    delivery_result: str
    ordered_at: datetime | None = None
    delivered_at: datetime | None = None
    recorded_by: UUID
    recorded_at: datetime
    notes: str | None = None


class SavingRecord(BaseModel):
    id: UUID
    purchase_record_id: UUID
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    status: Literal["pending", "verified"]
    baseline_policy: Literal["last_paid", "rolling_average_6m", "none_available"]
    baseline_source_landed_cost_ids: list[UUID]
    baseline_unit_price: Money | None = None
    baseline_value: Money | None = None
    actual_value: Money
    delta: Money | None = None
    calculation_version: str
    calculation_inputs: dict[str, Any]
    recorded_by: UUID
    recorded_at: datetime
    verified_by: UUID | None = None
    verified_at: datetime | None = None


class PurchaseOutcomeCreated(BaseModel):
    purchase_record: PurchaseRecord
    saving_record: SavingRecord


class SavingList(BaseModel):
    items: list[SavingRecord]
    next_cursor: str | None


class SavingEvidence(BaseModel):
    saving_record: SavingRecord
    purchase_record: PurchaseRecord
    quotation: dict[str, Any] | None = None
    match_decision: dict[str, Any] | None = None
    competing_offers: list[dict[str, Any]]
    calculation: dict[str, Any]
