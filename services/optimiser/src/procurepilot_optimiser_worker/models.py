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


class QuantityTier(StrictModel):
    workspace_product_id: UUID | None = None
    min_quantity: StrictStr
    unit_price: Money
    source_term_id: UUID | None = None

    @property
    def min_quantity_decimal(self) -> Decimal:
        return Decimal(self.min_quantity)


class SupplierCommercialTerms(StrictModel):
    supplier_id: UUID
    rule_version: StrictStr
    minimum_order_value: Money | None = None
    delivery_fee: Money | None = None
    free_delivery_threshold: Money | None = None
    quantity_tiers: list[QuantityTier] = Field(default_factory=list)
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class OptimisationHardConstraints(StrictModel):
    excluded_supplier_ids: list[UUID] = Field(default_factory=list)
    requested_delivery_by: datetime | None = None
    max_supplier_risk: StrictStr | None = None

    @property
    def max_supplier_risk_decimal(self) -> Decimal | None:
        if self.max_supplier_risk is None:
            return None
        return Decimal(self.max_supplier_risk)


class OptimisationSoftWeights(StrictModel):
    preferred_supplier: StrictStr = "0.0000"
    risk: StrictStr = "0.0000"
    lead_time: StrictStr = "0.0000"
    quality: StrictStr = "0.0000"
    price_competitiveness: StrictStr = "1.0000"


class SupplierRiskSignal(StrictModel):
    supplier_id: UUID
    risk_score: StrictStr
    confidence: StrictStr
    insufficient_evidence: bool
    source_ids: list[UUID] = Field(default_factory=list)
    rule_version: StrictStr

    @property
    def risk_score_decimal(self) -> Decimal:
        return Decimal(self.risk_score)


class AdvancedBasketRequest(StrictModel):
    id: UUID
    tenant_id: UUID
    supplier_ids: list[UUID] = Field(min_length=2, max_length=10)
    items: list[BasketItem] = Field(min_length=1, max_length=50)
    hard_constraints: OptimisationHardConstraints = Field(
        default_factory=OptimisationHardConstraints
    )
    soft_weights: OptimisationSoftWeights = Field(default_factory=OptimisationSoftWeights)
    rule_version: StrictStr

    @model_validator(mode="after")
    def _selected_suppliers_are_unique_and_not_all_excluded(self) -> AdvancedBasketRequest:
        if len(set(self.supplier_ids)) != len(self.supplier_ids):
            raise ValueError("advanced basket optimisation requires unique suppliers")
        selected = set(self.supplier_ids)
        excluded = set(self.hard_constraints.excluded_supplier_ids)
        if selected and selected.issubset(excluded):
            raise ValueError("supplier exclusions leave no eligible suppliers")
        return self


class AdvancedOfferInput(OfferInput):
    unit_landed_cost: Money
    source_landed_cost_id: UUID
    preferred: bool = False
    lead_time_days: int | None = Field(default=None, ge=0)


class AdvancedOptimisationInput(StrictModel):
    request: AdvancedBasketRequest
    offers: list[AdvancedOfferInput] = Field(min_length=1)
    supplier_terms: list[SupplierCommercialTerms] = Field(default_factory=list)
    supplier_risks: list[SupplierRiskSignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def _money_uses_one_currency(self) -> AdvancedOptimisationInput:
        currencies: set[str] = set()
        for offer in self.offers:
            currencies.add(offer.total_landed_cost.currency)
            currencies.add(offer.unit_landed_cost.currency)
        for terms in self.supplier_terms:
            for money in (
                terms.minimum_order_value,
                terms.delivery_fee,
                terms.free_delivery_threshold,
            ):
                if money is not None:
                    currencies.add(money.currency)
            for tier in terms.quantity_tiers:
                currencies.add(tier.unit_price.currency)
        if len(currencies) > 1:
            raise ValueError("advanced optimisation refuses mixed currencies without FX rules")
        return self


class AppliedConstraint(StrictModel):
    kind: Literal[
        "minimum_order_value",
        "free_delivery_threshold",
        "delivery_fee",
        "quantity_tier",
        "risk_tolerance",
        "supplier_exclusion",
        "urgency",
    ]
    supplier_id: UUID | None = None
    workspace_product_id: UUID | None = None
    description: StrictStr
    source_ids: list[UUID] = Field(default_factory=list)


class ViolatedConstraint(StrictModel):
    kind: Literal[
        "no_eligible_supplier",
        "minimum_order_value",
        "risk_tolerance",
        "supplier_exclusion",
        "urgency",
        "mixed_currency",
    ]
    supplier_id: UUID | None = None
    workspace_product_id: UUID | None = None
    requested_quantity: StrictStr | None = None
    message: StrictStr
    source_ids: list[UUID] = Field(default_factory=list)


class RiskNote(StrictModel):
    supplier_id: UUID
    severity: Literal["low", "medium", "high"]
    message: StrictStr
    confidence: StrictStr
    source_ids: list[UUID] = Field(default_factory=list)


class OptimisationConfidence(StrictModel):
    score: StrictStr
    insufficient_evidence: bool
    reasons: list[StrictStr] = Field(default_factory=list)


class AdvancedBasketResult(StrictModel):
    feasible: bool
    allocation: list[SupplierAllocation]
    total_landed_cost: Money | None
    single_supplier_baselines: list[SingleSupplierBaseline]
    applied_constraints: list[AppliedConstraint]
    violated_constraints: list[ViolatedConstraint]
    risk_notes: list[RiskNote]
    confidence: OptimisationConfidence
    valid_until: datetime
    source_landed_cost_ids: list[UUID]
    solver_version: StrictStr
    rule_version: StrictStr
    computed_at: datetime
    advisory_only: Literal[True] = True
