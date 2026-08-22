from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

RecommendationConfidence = Literal["high", "medium", "low"]
RiskNote = Literal[
    "price_expiring_soon", "low_match_confidence", "low_supplier_reliability"
]
StockSignal = Literal["in_stock", "low_stock", "out_of_stock", "unknown"]
BasketStatus = Literal["queued", "running", "completed", "failed"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class ProductRef(BaseModel):
    id: UUID
    tenant_name: str


class Offer(BaseModel):
    id: UUID
    workspace_product_id: UUID
    supplier_id: UUID
    supplier_name: str
    quotation_line_id: UUID
    match_decision_id: UUID
    landed_cost: Money
    normalised_unit_price: Money
    requested_quantity: str
    base_unit: str
    lead_time_days: int | None = None
    reliability_score: str | None = None
    stock_signal: StockSignal | None = None
    match_confidence: str
    valid_from: datetime
    valid_to: datetime | None = None
    is_expired: bool
    rule_version: str
    recorded_at: datetime


class RecommendationEvidence(StrictApiModel):
    weights: dict[str, str]
    components: dict[str, str]
    winning_margin: str | None
    tie_break: dict[str, object]


class Recommendation(BaseModel):
    recommended_offer_id: UUID
    score: str
    confidence: RecommendationConfidence
    valid_from: datetime
    valid_to: datetime | None = None
    risk_notes: list[RiskNote]
    evidence: RecommendationEvidence


class OfferList(BaseModel):
    items: list[Offer]
    next_cursor: str | None = None


class OfferComparison(BaseModel):
    product: ProductRef
    requested_quantity: str
    offers: list[Offer]
    recommendation: Recommendation | None


class PriceHistoryPoint(BaseModel):
    landed_cost_id: UUID
    workspace_product_id: UUID
    supplier_id: UUID
    supplier_name: str
    recorded_at: datetime
    valid_from: datetime
    valid_to: datetime | None = None
    normalised_unit_price: Money
    landed_cost_total: Money
    quantity: str
    base_unit: str


class PriceHistoryMetric(BaseModel):
    value: Money
    source_landed_cost_ids: list[UUID]


class PriceHistorySummary(BaseModel):
    last_paid: PriceHistoryMetric | None
    average_paid_rolling_window: PriceHistoryMetric | None
    best_price: PriceHistoryMetric | None


class PriceHistoryResponse(BaseModel):
    product: ProductRef
    window_months: int
    points: list[PriceHistoryPoint]
    summary: PriceHistorySummary
    next_cursor: str | None = None


class BasketItemRequest(StrictApiModel):
    workspace_product_id: UUID
    # Denominated in the product's normalised base unit, never a count of the supplier's
    # original pack/case — same convention as the compare `quantity` query parameter.
    quantity: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")


class BasketOptimiseRequest(StrictApiModel):
    supplier_ids: list[UUID] = Field(min_length=2, max_length=2)
    items: list[BasketItemRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct_suppliers_and_positive_quantities(self) -> BasketOptimiseRequest:
        if len(set(self.supplier_ids)) != 2:
            raise ValueError("supplier_ids must contain exactly two unique suppliers")
        return self


class AllocatedBasketLine(BaseModel):
    workspace_product_id: UUID
    quantity: str
    offer_id: UUID
    landed_cost: Money


class SupplierAllocation(BaseModel):
    supplier_id: UUID
    lines: list[AllocatedBasketLine]
    total_landed_cost: Money


class SingleSupplierBaseline(BaseModel):
    supplier_id: UUID
    feasible: bool
    total_landed_cost: Money | None


class InfeasibleBasketItem(BaseModel):
    workspace_product_id: UUID
    requested_quantity: str
    reason: Literal["no_offer_from_named_suppliers"]
    missing_supplier_ids: list[UUID]


class BasketSplitResult(BaseModel):
    feasible: bool
    allocation: list[SupplierAllocation]
    total_landed_cost: Money | None
    infeasible_items: list[InfeasibleBasketItem]
    computed_at: datetime
    single_supplier_baselines: list[SingleSupplierBaseline] = Field(default_factory=list)
    solver_version: str | None = None


class BasketSplitJob(BaseModel):
    id: UUID
    supplier_ids: list[UUID]
    items: list[BasketItemRequest]
    status: BasketStatus
    created_at: datetime
    result_url: str
    result: BasketSplitResult | None = None
    error: dict[str, object] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
