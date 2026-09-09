from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from procurepilot_api.modules.catalogue.models import ProductCreate
from procurepilot_api.modules.quotations.schemas import Money, Pack

MatchTaskStatus = Literal["open", "in_progress", "resolved"]
MatchTaskStatusFilter = Literal["open", "in_progress", "resolved", "all"]
MatchTaskPriority = Literal["low", "normal", "high"]
MatchTaskReason = Literal["low_confidence", "close_candidates", "no_candidate", "alias_conflict"]
QuotedExposureIssue = Literal["currency_mismatch"]
MatchOutcome = Literal[
    "same_product",
    "different_pack",
    "different_variant",
    "compatible_alternative",
    "no_match_new_product",
]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeatureScore(BaseModel):
    brand_match: str
    variant_match: str
    pack_unit_match: str
    pack_size_plausibility: str
    price_plausibility: str


class MatchReason(BaseModel):
    alias_hit: bool
    gtin_match: bool
    supplier_code_match: bool
    lexical_similarity: str
    semantic_similarity: str
    feature_score: FeatureScore


class ProductSummary(BaseModel):
    id: UUID
    tenant_name: str
    brand: str | None = None
    canonical_name: str
    variant: str | None = None
    gtin: str | None = None
    base_unit: str
    status: Literal["active", "archived"]


class QuotationLineSummary(BaseModel):
    id: UUID
    line_number: int = Field(ge=1)
    original_text: str
    quantity: str | None = None
    pack: Pack | None = None
    unit_price: Money | None = None
    vat_rate: str | None = None
    delivery_fee: Money | None = None
    discount: Money | None = None
    quoted_line_total: Money | None = None
    quoted_line_total_issue: QuotedExposureIssue | None = None


class MatchCandidate(BaseModel):
    id: UUID
    quotation_line_id: UUID
    candidate_product: ProductSummary
    confidence: str = Field(
        description=(
            "Heuristic weighted match score used to rank and route candidates; "
            "not a calibrated probability."
        )
    )
    reasons: MatchReason
    rank: int = Field(ge=1)
    scoring_version: str | None = None
    embedding_model: str | None = None
    created_at: datetime


class MatchDecision(BaseModel):
    id: UUID
    quotation_line_id: UUID
    matched_product: ProductSummary
    selected_match_candidate_id: UUID | None = None
    outcome: MatchOutcome
    is_automatic: bool
    decided_by: UUID | None = None
    decided_at: datetime
    confidence: str = Field(
        description=(
            "Heuristic weighted match score recorded for the decision; "
            "not a calibrated probability."
        )
    )
    alias_id: UUID | None = None


class QuotationMatchSummary(BaseModel):
    id: UUID
    status: str
    document_id: UUID | None = None
    source_filename: str | None = None
    issue_date: date | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    reviewed_by_email: str | None = None
    line_count: int = Field(ge=0)
    open_match_task_count: int = Field(ge=0)
    supplier_name: str | None = None


class MatchTask(BaseModel):
    id: UUID
    quotation_id: UUID | None = None
    quotation: QuotationMatchSummary
    quotation_line: QuotationLineSummary
    status: MatchTaskStatus
    priority: MatchTaskPriority
    reason: MatchTaskReason
    candidates: list[MatchCandidate]
    decision: MatchDecision | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    supplier_name: str | None = None


class MatchResolutionRequest(StrictApiModel):
    outcome: MatchOutcome
    selected_match_candidate_id: UUID | None = None
    create_product: ProductCreate | None = None

    @model_validator(mode="after")
    def _consistent_payload(self) -> MatchResolutionRequest:
        if self.outcome == "no_match_new_product":
            if self.create_product is None:
                raise ValueError("create_product is required for no_match_new_product")
            if self.selected_match_candidate_id is not None:
                raise ValueError(
                    "selected_match_candidate_id is not allowed for no_match_new_product"
                )
        elif self.selected_match_candidate_id is None:
            raise ValueError(
                "selected_match_candidate_id is required for existing-product outcomes"
            )
        return self


class MatchTaskList(BaseModel):
    items: list[MatchTask]
    next_cursor: str | None = None


class QuotationLineMatchState(BaseModel):
    line: QuotationLineSummary
    candidates: list[MatchCandidate]
    task: MatchTask | None = None
    decision: MatchDecision | None = None
    landed_cost: Any | None = None


class QuotationMatches(BaseModel):
    quotation_id: UUID
    lines: list[QuotationLineMatchState]


class MoneyInput(BaseModel):
    amount: StrictStr
    currency: StrictStr
