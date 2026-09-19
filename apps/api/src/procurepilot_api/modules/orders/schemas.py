from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OrderStatus = Literal[
    "draft",
    "submitted",
    "confirmed",
    "partially_received",
    "received",
    "cancelled",
    "closed",
]
SourceKind = Literal["manual", "import", "provider"]
EvidenceState = Literal["pending", "available", "unavailable"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_unsafe_scalar_coercions(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid for this boundary")
        if isinstance(value, str) and not value.strip():
            raise ValueError("whitespace-only strings are not valid")
        return value


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return value


def _require_scale(value: Decimal, places: int, field: str) -> Decimal:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -places:
        raise ValueError(f"{field} supports at most {places} fractional places")
    return value


class Money(StrictModel):
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")

    _validate_scale = field_validator("amount")(
        lambda value: _require_scale(value, 4, "money amount")
    )


class PurchaseOrderLine(StrictModel):
    id: UUID
    line_number: int = Field(gt=0)
    workspace_product_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    ordered_quantity: Decimal = Field(ge=0)
    base_unit: str = Field(min_length=1, max_length=100)
    unit_price: Money
    tax: Money
    line_total: Money

    _validate_quantity_scale = field_validator("ordered_quantity")(
        lambda value: _require_scale(value, 6, "ordered quantity")
    )

    @model_validator(mode="after")
    def validate_currency_relationships(self) -> PurchaseOrderLine:
        if self.line_total.currency != self.unit_price.currency:
            raise ValueError("line total and unit price currencies must match")
        if self.tax.amount != 0 and self.tax.currency != self.line_total.currency:
            raise ValueError("non-zero line tax must use the line total currency")
        return self


class PurchaseOrder(StrictModel):
    id: UUID
    tenant_id: UUID
    order_number: str = Field(min_length=1, max_length=100)
    supplier_id: UUID
    status: OrderStatus
    order_date: date
    expected_delivery_date: date | None = None
    total: Money
    tax: Money
    source_kind: SourceKind
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    lines: tuple[PurchaseOrderLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_header(self) -> PurchaseOrder:
        if (
            self.expected_delivery_date is not None
            and self.expected_delivery_date < self.order_date
        ):
            raise ValueError("expected delivery date cannot precede order date")
        if self.tax.amount != 0 and self.tax.currency != self.total.currency:
            raise ValueError("non-zero order tax must use the total currency")
        line_numbers = [line.line_number for line in self.lines]
        line_ids = [line.id for line in self.lines]
        if len(set(line_numbers)) != len(line_numbers):
            raise ValueError("order line numbers must be unique")
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("order line identifiers must be unique")
        if any(line.line_total.currency != self.total.currency for line in self.lines):
            raise ValueError("all line totals must use the order currency")
        if sum((line.line_total.amount for line in self.lines), Decimal("0")) != self.total.amount:
            raise ValueError("order total must equal the sum of line totals")
        return self

    _validate_datetimes = field_validator("created_at", "updated_at")(_require_aware)


class SupplierConfirmationLine(StrictModel):
    id: UUID
    purchase_order_line_id: UUID
    confirmed_quantity: Decimal = Field(ge=0)
    confirmed_unit_price: Money | None = None

    _validate_quantity_scale = field_validator("confirmed_quantity")(
        lambda value: _require_scale(value, 6, "confirmed quantity")
    )


class SupplierConfirmation(StrictModel):
    id: UUID
    tenant_id: UUID
    purchase_order_id: UUID
    supplier_reference: str = Field(min_length=1, max_length=200)
    confirmed_at: datetime
    expected_delivery_date: date | None = None
    source_kind: SourceKind
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    recorded_by: UUID
    created_at: datetime
    lines: tuple[SupplierConfirmationLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lines(self) -> SupplierConfirmation:
        line_ids = [line.purchase_order_line_id for line in self.lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("confirmation lines must identify unique order lines")
        return self

    _validate_datetimes = field_validator("confirmed_at", "created_at")(_require_aware)


class DeliveryReceiptLine(StrictModel):
    id: UUID
    purchase_order_line_id: UUID
    received_quantity: Decimal = Field(ge=0)

    _validate_quantity_scale = field_validator("received_quantity")(
        lambda value: _require_scale(value, 6, "received quantity")
    )


class DeliveryReceipt(StrictModel):
    id: UUID
    tenant_id: UUID
    purchase_order_id: UUID
    receipt_reference: str = Field(min_length=1, max_length=200)
    receipt_date: date
    received_by: UUID
    source_kind: SourceKind
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    created_at: datetime
    lines: tuple[DeliveryReceiptLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lines(self) -> DeliveryReceipt:
        line_ids = [line.purchase_order_line_id for line in self.lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("receipt lines must identify unique order lines")
        return self

    _validate_datetimes = field_validator("created_at")(_require_aware)


class EvidenceProjection(StrictModel):
    state: EvidenceState
    quantity: Decimal | None = Field(default=None, ge=0)
    source_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_state_value(self) -> EvidenceProjection:
        if self.state == "available" and (self.quantity is None or not self.source_ids):
            raise ValueError("available evidence requires a quantity and source")
        if self.state != "available" and self.quantity is not None:
            raise ValueError("pending or unavailable evidence cannot carry a quantity")
        if self.state != "available" and self.source_ids:
            raise ValueError("pending or unavailable evidence cannot carry a source")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("evidence source identifiers must be unique")
        return self


class LifecycleLineSummary(StrictModel):
    purchase_order_line_id: UUID
    ordered_quantity: Decimal = Field(ge=0)
    confirmed: EvidenceProjection
    received: EvidenceProjection
    remaining_quantity: Decimal | None = Field(default=None, ge=0)
    over_received_quantity: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_receipt_variance(self) -> LifecycleLineSummary:
        if self.received.state == "available":
            if self.remaining_quantity is None or self.over_received_quantity is None:
                raise ValueError("available receipt evidence requires variance values")
        elif self.remaining_quantity is not None or self.over_received_quantity is not None:
            raise ValueError("missing receipt evidence cannot carry variance values")
        return self


class LifecycleSummary(StrictModel):
    purchase_order_id: UUID
    status: OrderStatus
    confirmation: EvidenceState
    receipt: EvidenceState
    lines: tuple[LifecycleLineSummary, ...] = Field(min_length=1)


class OrderEvidenceProjection(StrictModel):
    order: PurchaseOrder
    confirmation: SupplierConfirmation | None = None
    receipts: tuple[DeliveryReceipt, ...] = ()
    lifecycle: LifecycleSummary


class PurchaseOrderLineInput(StrictModel):
    line_number: int = Field(gt=0)
    workspace_product_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    ordered_quantity: Decimal = Field(ge=0)
    base_unit: str = Field(min_length=1, max_length=100)
    unit_price: Money
    tax: Money
    line_total: Money

    _validate_quantity_scale = field_validator("ordered_quantity")(
        lambda value: _require_scale(value, 6, "ordered quantity")
    )


class PurchaseOrderCreate(StrictModel):
    order_number: str = Field(min_length=1, max_length=100)
    supplier_id: UUID
    order_date: date
    expected_delivery_date: date | None = None
    total: Money
    tax: Money
    source_kind: SourceKind = "manual"
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    lines: tuple[PurchaseOrderLineInput, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_totals(self) -> PurchaseOrderCreate:
        if (
            self.expected_delivery_date is not None
            and self.expected_delivery_date < self.order_date
        ):
            raise ValueError("expected delivery date cannot precede order date")
        if self.tax.amount != 0 and self.tax.currency != self.total.currency:
            raise ValueError("non-zero order tax must use the total currency")
        if any(line.line_total.currency != self.total.currency for line in self.lines):
            raise ValueError("all line totals must use the order currency")
        if sum((line.line_total.amount for line in self.lines), Decimal("0")) != self.total.amount:
            raise ValueError("order total must equal the sum of line totals")
        line_numbers = [line.line_number for line in self.lines]
        if len(set(line_numbers)) != len(line_numbers):
            raise ValueError("order line numbers must be unique")
        return self


class SupplierConfirmationLineInput(StrictModel):
    purchase_order_line_id: UUID
    confirmed_quantity: Decimal = Field(ge=0)
    confirmed_unit_price: Money | None = None

    _validate_quantity_scale = field_validator("confirmed_quantity")(
        lambda value: _require_scale(value, 6, "confirmed quantity")
    )


class SupplierConfirmationCreate(StrictModel):
    supplier_reference: str = Field(min_length=1, max_length=200)
    confirmed_at: datetime
    expected_delivery_date: date | None = None
    source_kind: SourceKind = "manual"
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    lines: tuple[SupplierConfirmationLineInput, ...] = Field(min_length=1)

    _validate_datetime = field_validator("confirmed_at")(_require_aware)


class DeliveryReceiptLineInput(StrictModel):
    purchase_order_line_id: UUID
    received_quantity: Decimal = Field(ge=0)

    _validate_quantity_scale = field_validator("received_quantity")(
        lambda value: _require_scale(value, 6, "received quantity")
    )


class DeliveryReceiptCreate(StrictModel):
    receipt_reference: str = Field(min_length=1, max_length=200)
    receipt_date: date
    source_kind: SourceKind = "manual"
    source_reference: str = Field(min_length=1, max_length=500)
    source_hash: str | None = None
    lines: tuple[DeliveryReceiptLineInput, ...] = Field(min_length=1)


class PurchaseOrderList(StrictModel):
    items: tuple[PurchaseOrder, ...]
    next_cursor: str | None = None
