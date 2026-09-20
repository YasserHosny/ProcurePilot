from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ForecastState = Literal["ready", "provisional", "insufficient_data"]
ForecastConfidence = Literal["high", "medium", "low"]
ProposalStatus = Literal["open", "prepared", "dismissed", "expired"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReorderProposal(BaseModel):
    id: UUID
    demand_forecast_id: UUID
    workspace_product_id: UUID
    product_name: str
    status: ProposalStatus
    horizon_days: int
    source_window_start: date
    source_window_end: date
    observed_history_days: int | None
    expected_daily_demand: str | None
    expected_demand: str | None
    uncertainty_lower: str | None
    uncertainty_upper: str | None
    stock_on_hand: str | None
    suggested_quantity: str | None
    confidence: ForecastConfidence
    state: ForecastState
    release_posture: Literal["g3_unmet"]
    valid_from: datetime
    valid_until: datetime
    purchase_request_id: UUID | None = None
    prepared_branch_id: UUID | None = None
    created_at: datetime

    @field_validator(
        "expected_daily_demand",
        "expected_demand",
        "uncertainty_lower",
        "uncertainty_upper",
        "stock_on_hand",
        "suggested_quantity",
        mode="before",
    )
    @classmethod
    def _decimal_to_string(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, (Decimal, int, float)):
            return str(value)
        return str(value)


class ReorderProposalList(BaseModel):
    items: list[ReorderProposal]
    next_cursor: str | None = None


class RecomputeResponse(BaseModel):
    generated_forecasts: int = Field(ge=0)
    open_proposals: int = Field(ge=0)
    release_posture: Literal["g3_unmet"] = "g3_unmet"


class PrepareRequestInput(StrictApiModel):
    branch_id: UUID
    required_by_date: date
    cost_centre_id: UUID | None = None


class PrepareRequestResponse(BaseModel):
    proposal: ReorderProposal
    purchase_request_id: UUID
