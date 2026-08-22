from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictModel):
    amount: StrictStr
    currency: StrictStr


class BasketItem(StrictModel):
    workspace_product_id: UUID
    # Denominated in the product's normalised base unit, never a count of the supplier's
    # original pack/case — see repository.read_current_offers.
    quantity: StrictStr

    @property
    def quantity_decimal(self) -> Decimal:
        return Decimal(self.quantity)


class BasketJob(StrictModel):
    id: UUID
    tenant_id: UUID
    supplier_ids: list[UUID] = Field(min_length=2, max_length=2)
    items: list[BasketItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _exactly_two_unique_suppliers(self) -> BasketJob:
        if len(set(self.supplier_ids)) != 2:
            raise ValueError("basket split requires exactly two unique suppliers")
        return self


class OfferInput(StrictModel):
    offer_id: UUID
    workspace_product_id: UUID
    supplier_id: UUID
    quantity: StrictStr
    total_landed_cost: Money

    @property
    def amount(self) -> Decimal:
        return Decimal(self.total_landed_cost.amount)


class AllocatedBasketLine(StrictModel):
    workspace_product_id: UUID
    quantity: StrictStr
    offer_id: UUID
    landed_cost: Money


class SupplierAllocation(StrictModel):
    supplier_id: UUID
    lines: list[AllocatedBasketLine]
    total_landed_cost: Money


class SingleSupplierBaseline(StrictModel):
    supplier_id: UUID
    feasible: bool
    total_landed_cost: Money | None


class InfeasibleBasketItem(StrictModel):
    workspace_product_id: UUID
    requested_quantity: StrictStr
    reason: Literal["no_offer_from_named_suppliers"]
    missing_supplier_ids: list[UUID]


class BasketSplitResult(StrictModel):
    feasible: bool
    allocation: list[SupplierAllocation]
    total_landed_cost: Money | None
    single_supplier_baselines: list[SingleSupplierBaseline]
    infeasible_items: list[InfeasibleBasketItem]
    solver_version: str
    computed_at: datetime
