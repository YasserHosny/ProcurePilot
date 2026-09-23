"""Pydantic v2 schemas for the Grounded Procurement Analyst module (R4.2).

Every AnalystTurnResponse carries ``release_posture = "g3_unmet"`` per FR-011.
Monetary amounts use the shared Money type (amount + currency, no bare numbers).
AnalystCategory is a real StrEnum so its string values have a stable identity
and cannot silently collide with bare Literals in other modules.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AnalystCategory(enum.StrEnum):
    """Supported FR-002 question categories.

    A real StrEnum rather than a bare Literal so the set of valid categories
    has a single source of truth that retrieval.py, schemas, and future intent.py
    can all import without risk of string-value divergence.
    """

    spend_savings = "spend_savings"
    supplier_performance_risk = "supplier_performance_risk"
    orders_quotations = "orders_quotations"
    reorder_forecasts = "reorder_forecasts"


class CitationSourceKind(enum.StrEnum):
    """The seven source-record kinds an AnalystCitation may reference (FR-003)."""

    purchase_order = "purchase_order"
    quotation_line = "quotation_line"
    landed_cost = "landed_cost"
    saving_record = "saving_record"
    supplier_scorecard_snapshot = "supplier_scorecard_snapshot"
    delivery_receipt = "delivery_receipt"
    reorder_proposal = "reorder_proposal"


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------


class AnalystCitationResponse(StrictApiModel):
    """One typed, tenant-pinned source reference from a turn — one source kind per row."""

    id: UUID
    turn_id: UUID
    source_kind: CitationSourceKind
    source_id: UUID
    created_at: datetime


class AnalystCitationCreate(StrictApiModel):
    """What the service layer creates for each citation row."""

    source_kind: CitationSourceKind
    source_id: UUID


# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------


class CalculationDetail(StrictApiModel):
    """The explicit calculation the analyst performed (FR-004).

    ``inputs`` is an ordered list of labelled Money or plain string values that
    fed the formula.  ``formula`` is a human-readable description (e.g.
    "sum of landed costs").  ``result`` is the final answer value.
    """

    inputs: list[dict[str, object]] = Field(default_factory=list)
    formula: str
    result: Money | str | None = None


class AnalystTurnResponse(StrictApiModel):
    """One question/answer turn — immutable once created (FR-010).

    ``release_posture`` is always ``"g3_unmet"`` per FR-011.
    ``next_step_url`` is present only when the answer concerns an entity with
    an existing actionable surface (FR-003A).
    """

    id: UUID
    conversation_id: UUID
    creating_member_id: UUID
    question_text: str
    category: AnalystCategory
    answer_text: str
    calculation_version: str
    release_posture: Literal["g3_unmet"] = "g3_unmet"
    calculation: CalculationDetail | None = None
    citations: list[AnalystCitationResponse] = Field(default_factory=list)
    next_step_url: str | None = None
    created_at: datetime


class AnalystTurnCreate(StrictApiModel):
    """Request body for adding a turn to a conversation."""

    question_text: StrictStr = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class AnalystConversationResponse(StrictApiModel):
    """A tenant- and member-scoped thread of question/answer turns (FR-008)."""

    id: UUID
    tenant_id: UUID
    creating_member_id: UUID
    created_at: datetime
    turns: list[AnalystTurnResponse] = Field(default_factory=list)


class AnalystConversationCreate(StrictApiModel):
    """Request body for starting a new conversation (first question included)."""

    question_text: StrictStr = Field(min_length=1, max_length=4000)


class AnalystConversationList(StrictApiModel):
    items: list[AnalystConversationResponse]
    next_cursor: str | None = None
