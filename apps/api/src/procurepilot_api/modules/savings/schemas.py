from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from procurepilot_api.modules.catalogue.units import canonical_base_unit

MoneyAmount = Decimal
BaselinePolicy = Literal["last_po_price", "last_paid", "rolling_average_6m", "none_available"]
DeliveryResult = Literal["ordered", "partially_delivered", "delivered", "cancelled", "disputed"]


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
    # Set when the outcome is recorded from a purchase order line (finding 22); the baseline then
    # excludes that purchase order.
    purchase_order_line_id: UUID | None = None
    quantity: Decimal = Field(gt=0, decimal_places=6)
    base_unit: str
    unit_price: Money
    total_paid: Money
    delivery_result: DeliveryResult
    ordered_at: datetime | None = None
    delivered_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("base_unit", mode="before")
    @classmethod
    def _canonical_base_unit(cls, value: object) -> object:
        return canonical_base_unit(value) if isinstance(value, str) else value


class PurchaseRecord(BaseModel):
    id: UUID
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    quotation_line_id: UUID | None = None
    match_decision_id: UUID | None = None
    landed_cost_id: UUID | None = None
    purchase_order_line_id: UUID | None = None
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
    baseline_policy: BaselinePolicy
    baseline_source_landed_cost_ids: list[UUID]
    baseline_source_po_line_ids: list[UUID] | None = None
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


class PurchaseOutcomePrefillLine(BaseModel):
    """One PO line converted to an outcome line: base units and per-base-unit price (ADR-020)."""

    purchase_order_line_id: UUID
    line_number: int
    description: str
    workspace_product_id: UUID | None = None
    ordered_packs: Decimal
    pack_base_quantity: Decimal | None = None
    quantity: Decimal
    base_unit: str
    unit_price: Money
    total_paid: Money
    tax: Money
    recordable: bool
    reason: Literal["no_product", "zero_quantity", "already_recorded"] | None = None
    recorded_saving_id: UUID | None = None


class PurchaseOutcomePrefill(BaseModel):
    purchase_order_id: UUID
    order_number: str
    status: str
    supplier_id: UUID
    order_date: date
    delivery_result: DeliveryResult
    lines: list[PurchaseOutcomePrefillLine]
