from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictStr,
    field_validator,
    model_validator,
)

RecommendationConfidence = Literal["high", "medium", "low"]
FreshnessStatus = Literal["fresh", "stale"]
RiskNote = Literal[
    "price_expiring_soon",
    "low_match_confidence",
    "low_supplier_reliability",
    "high_supplier_risk",
    "elevated_supplier_risk",
]
StockSignal = Literal["in_stock", "low_stock", "out_of_stock", "unknown"]
BasketStatus = Literal["queued", "running", "completed", "failed"]
RiskTolerance = Literal["low", "medium", "high"]
BasketUrgency = Literal["normal", "urgent"]
EvidenceConfidence = Literal["high", "medium", "low"]
ConstraintKind = Literal[
    "minimum_order_value",
    "free_delivery_threshold",
    "delivery_fee",
    "quantity_tier",
    "supplier_exclusion",
    "urgency",
    "currency_consistency",
]
AnomalyAlertKind = Literal[
    "price_spike",
    "likely_duplicate_quotation_line",
    "decimal_or_quantity_anomaly",
    "delivery_cost_anomaly",
    "supplier_quality_trend_change",
]
BriefItemKind = Literal[
    "price_trajectory",
    "alternatives",
    "service_performance",
    "concentration_volume",
    "payment_context",
    "purchase_pattern",
]
BriefStatus = Literal["prepared", "acknowledged", "dismissed"]


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
    freshness_score: str = "1.0000"
    freshness_age_days: int = 0
    freshness_status: FreshnessStatus = "fresh"
    freshness_due_at: datetime | None = None


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


class OptimisationWeights(StrictApiModel):
    price: float = Field(ge=0, le=1)
    preferred_supplier: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    lead_time: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)


class AdvancedBasketOptimiseRequest(StrictApiModel):
    supplier_ids: list[UUID] = Field(min_length=2, max_length=10)
    items: list[BasketItemRequest] = Field(min_length=1, max_length=50)
    risk_tolerance: RiskTolerance
    urgency: BasketUrgency
    weights: OptimisationWeights
    excluded_supplier_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_supplier_sets(self) -> AdvancedBasketOptimiseRequest:
        supplier_ids = set(self.supplier_ids)
        if len(supplier_ids) != len(self.supplier_ids):
            raise ValueError("supplier_ids must contain unique suppliers")
        excluded_ids = set(self.excluded_supplier_ids)
        if len(excluded_ids) != len(self.excluded_supplier_ids):
            raise ValueError("excluded_supplier_ids must contain unique suppliers")
        unknown_exclusions = excluded_ids - supplier_ids
        if unknown_exclusions:
            raise ValueError("excluded_supplier_ids must be selected suppliers")
        if len(supplier_ids - excluded_ids) < 1:
            raise ValueError("at least one selected supplier must remain eligible")
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


class OptimisationConstraint(StrictApiModel):
    kind: ConstraintKind
    supplier_id: UUID | None = None
    workspace_product_id: UUID | None = None
    description: str
    money: Money | None = None
    source_ids: list[UUID] = Field(default_factory=list)


class ViolatedOptimisationConstraint(OptimisationConstraint):
    reason: str


class AdvancedBasketAllocationLine(StrictApiModel):
    workspace_product_id: UUID
    supplier_id: UUID
    quantity: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")
    offer_id: UUID
    landed_cost: Money
    applied_tier_id: str | None = None


class AdvancedSupplierAllocation(StrictApiModel):
    supplier_id: UUID
    lines: list[AdvancedBasketAllocationLine]
    total_landed_cost: Money


class AdvancedSingleSupplierBaseline(StrictApiModel):
    supplier_id: UUID
    feasible: bool
    total_landed_cost: Money | None = None
    violated_constraints: list[ViolatedOptimisationConstraint] = Field(default_factory=list)


class AdvancedBasketResult(StrictApiModel):
    feasible: bool
    allocation: list[AdvancedSupplierAllocation]
    total_landed_cost: Money | None = None
    single_supplier_baselines: list[AdvancedSingleSupplierBaseline] = Field(default_factory=list)
    applied_constraints: list[OptimisationConstraint]
    violated_constraints: list[ViolatedOptimisationConstraint]
    risk_notes: list[str]
    confidence: EvidenceConfidence
    source_landed_cost_ids: list[UUID]
    solver_version: str
    computed_at: datetime
    valid_until: datetime | None = None


class BasketSplitJob(BaseModel):
    id: UUID
    supplier_ids: list[UUID]
    items: list[BasketItemRequest]
    status: BasketStatus
    created_at: datetime
    result_url: str
    result: BasketSplitResult | AdvancedBasketResult | None = None
    error: dict[str, object] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SupplierQuantityTier(StrictApiModel):
    workspace_product_id: UUID | None = None
    min_quantity: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")
    unit_price: Money


class SupplierCommercialTermCreate(StrictApiModel):
    effective_from: datetime
    effective_to: datetime | None = None
    minimum_order_value: Money | None = None
    delivery_fee: Money | None = None
    free_delivery_threshold: Money | None = None
    quantity_tiers: list[SupplierQuantityTier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_effective_window(self) -> SupplierCommercialTermCreate:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class SupplierCommercialTerm(SupplierCommercialTermCreate):
    id: UUID
    supplier_id: UUID
    rule_version: str
    created_at: datetime


class SupplierCommercialTermList(StrictApiModel):
    items: list[SupplierCommercialTerm]


RefreshScheduleStatus = Literal["active", "paused", "due"]


class RefreshScheduleCreate(StrictApiModel):
    workspace_product_id: UUID
    supplier_id: UUID
    cadence_days: int = Field(default=14, ge=1, le=365)


class RefreshScheduleUpdate(StrictApiModel):
    cadence_days: int | None = Field(default=None, ge=1, le=365)
    status: RefreshScheduleStatus | None = None
    source_import_id: UUID | None = None


class RefreshSchedule(StrictApiModel):
    id: UUID
    workspace_product_id: UUID
    supplier_id: UUID
    cadence_days: int
    status: RefreshScheduleStatus
    next_refresh_at: datetime
    last_observed_at: datetime | None = None
    last_requested_at: datetime | None = None
    last_error: str | None = None
    source_import_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RefreshScheduleList(StrictApiModel):
    items: list[RefreshSchedule]
    next_cursor: str | None = None


class SupplierScoreMetric(StrictApiModel):
    value: str | None = None
    sample_count: int = Field(ge=0)
    source_ids: list[UUID] = Field(default_factory=list)
    confidence: EvidenceConfidence
    insufficient_evidence: bool
    window_start: date
    window_end: date


class SupplierRiskSubScore(StrictApiModel):
    name: str
    score: str
    weight: str
    evidence: dict[str, object]


class SupplierRiskScore(StrictApiModel):
    total: str
    confidence: EvidenceConfidence
    sub_scores: list[SupplierRiskSubScore]
    rule_version: str


class SupplierScorecard(StrictApiModel):
    supplier_id: UUID
    window_start: date
    window_end: date
    metrics: dict[str, SupplierScoreMetric]
    risk_score: SupplierRiskScore
    source_counts: dict[str, int]
    confidence: EvidenceConfidence
    insufficient_evidence: bool
    computed_at: datetime
    rule_version: str


class SupplierRiskSnapshot(StrictApiModel):
    id: UUID
    supplier_id: UUID
    window_start: date
    window_end: date
    state: Literal["ready", "provisional", "insufficient_data"]
    confidence: EvidenceConfidence
    release_posture: Literal["g3_unmet"]
    valid_from: datetime
    valid_until: datetime
    source_fingerprint: StrictStr
    observed_history_days: int = Field(ge=0)
    risk_score: dict[str, object]
    computed_at: datetime


class SupplierRiskList(StrictApiModel):
    items: tuple[SupplierRiskSnapshot, ...]
    next_cursor: str | None = None


class SupplierRiskRecomputeResponse(StrictApiModel):
    generated_snapshots: int = Field(ge=0)
    release_posture: Literal["g3_unmet"] = "g3_unmet"


class AnomalySignal(StrictApiModel):
    id: str
    kind: AnomalyAlertKind
    workspace_product_id: UUID
    supplier_id: UUID | None = None
    severity: Literal["info", "warning", "critical"]
    confidence: EvidenceConfidence
    evidence: dict[str, object]
    action: Literal[
        "compare_product",
        "inspect_supplier_scorecard",
        "review_quotation",
        "review_quality_history",
    ]
    created_from_current_data_at: datetime
    dismissed: bool
    valid_until: datetime | None = None


# V2 keeps Decimal values internally; only the JSON API representation is rounded.
RiskDecimal = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: _serialize_risk_decimal(value), return_type=str, when_used="json"
    ),
]


def _serialize_risk_decimal(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = max(28, value.adjusted() + 8 if value else 28)
        return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


class _ImmutableDict(dict):
    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("immutable result container")

    __delitem__ = __setitem__ = _immutable
    clear = pop = popitem = setdefault = update = _immutable

    def __ior__(self, value: object) -> _ImmutableDict:
        self._immutable(value)


class RiskCurrencyBucket(StrictApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    currency: str
    supplier_spend: RiskDecimal
    tenant_spend: RiskDecimal
    sample_count: int
    share: RiskDecimal | None
    source_ids: tuple[UUID, ...]


class RiskPriceComparison(StrictApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: UUID
    base_unit: str
    currency: str
    baseline_median: RiskDecimal
    current_median: RiskDecimal
    drift: RiskDecimal
    source_ids: tuple[UUID, ...]


class SupplierRiskEvidenceRef(StrictApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    source_kind: Literal[
        "purchase_order",
        "delivery_receipt_line",
        "landed_cost",
        "workspace_product",
    ]


class SupplierRiskComponentV2(StrictApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: RiskDecimal | None
    risk: RiskDecimal | None
    sample_count: int
    product_count: int = 0
    confidence: EvidenceConfidence
    insufficient_evidence: bool
    excluded_counts: dict[str, int]
    source_ids: tuple[UUID, ...]
    source_refs: tuple[SupplierRiskEvidenceRef, ...] = Field(default_factory=tuple)
    window_start: date
    split_date: date
    window_end: date
    calculation_version: str
    currency_buckets: tuple[RiskCurrencyBucket, ...] = Field(default_factory=tuple)
    price_comparisons: tuple[RiskPriceComparison, ...] = Field(default_factory=tuple)
    baseline_count: int = 0
    current_count: int = 0
    baseline_reliability: RiskDecimal | None = None
    current_reliability: RiskDecimal | None = None
    numerator: RiskDecimal | None = None
    denominator: RiskDecimal | None = None

    @field_validator("excluded_counts", mode="after")
    @classmethod
    def _freeze_excluded_counts(cls, value: dict[str, int]) -> dict[str, int]:
        return _ImmutableDict(value)


class SupplierRiskResult(StrictApiModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_id: UUID
    components: dict[str, SupplierRiskComponentV2]
    weights: dict[str, RiskDecimal]
    score: RiskDecimal | None
    risk_level: Literal["low", "medium", "high"] | None
    confidence: EvidenceConfidence
    state: Literal["ready", "provisional", "insufficient_data"]
    release_posture: Literal["g3_unmet"] = "g3_unmet"
    window_start: date
    split_date: date
    window_end: date
    observed_history_days: int
    scorecard_version: str
    risk_version: str
    source_fingerprint: str

    @field_validator("components", "weights", mode="after")
    @classmethod
    def _freeze_dicts(cls, value: dict[str, object]) -> dict[str, object]:
        return _ImmutableDict(value)


class NegotiationBriefItem(StrictApiModel):
    kind: BriefItemKind
    rank: int = Field(ge=1)
    value: str | None = None
    amount: Money | None = None
    confidence: EvidenceConfidence
    risk: str | None = None
    valid_from: date
    valid_until: date
    question_i18n_key: StrictStr
    calculation_version: StrictStr
    metric_id: UUID | None = None
    evidence_ids: tuple[UUID, ...] = ()


class NegotiationBrief(StrictApiModel):
    id: UUID
    supplier_id: UUID
    snapshot_id: UUID
    brief_version: StrictStr
    source_fingerprint: StrictStr
    release_posture: Literal["g3_unmet"]
    valid_from: datetime
    valid_until: datetime
    status: BriefStatus
    items: tuple[NegotiationBriefItem, ...]


class NegotiationBriefList(StrictApiModel):
    items: tuple[NegotiationBrief, ...]
    next_cursor: str | None = None


class NegotiationBriefDismissRequest(StrictApiModel):
    reason: StrictStr = Field(min_length=1, max_length=1000)
