"""Question-understanding (intent classification) for the Grounded Procurement Analyst (R4.2).

Mirrors the extraction-worker provider pattern exactly:
  - ``IntentProvider`` Protocol with ``method`` / ``model_version`` attributes.
  - ``BedrockIntentProvider``  — real AWS Bedrock/Claude call using the same boto3
    ``converse`` shape already established in the extraction worker (ADR-004/ADR-014).
  - ``FakeIntentProvider``     — deterministic, no network, selected by
    ANALYST_INTENT_PROVIDER_MODE=stub (matching EXTRACTION_PROVIDER_MODE's own convention).

FR-005 guarantee: the provider only classifies the *question* into a structured output
schema.  It NEVER generates answer text, numbers, or citations — those come exclusively
from retrieval.py.  The strict ``IntentResult`` Pydantic model enforces this at the
boundary: ``category`` is either one of the four FR-002 AnalystCategory values or the
literal string ``"unsupported"``.  No free text leaks through.

FR-008 follow-up wiring: ``classify`` accepts an optional ``prior_turn_context``
argument carrying the immediately preceding turn's resolved ``category`` and ``entities``.
The Bedrock call includes this context in its prompt so that omitted entities in a
follow-up question can be resolved from the prior turn.  The wiring is accepted here and
passed through; the full contextual-resolution behaviour is exercised in US3 (T026-T028).
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from procurepilot_api.modules.analyst.schemas import AnalystCategory

# ---------------------------------------------------------------------------
# Shared output schema
# ---------------------------------------------------------------------------


class IntentEntities(BaseModel):
    """Structured entities extracted from the question."""

    model_config = ConfigDict(extra="ignore")

    supplier_id: str | None = None
    product_id: str | None = None
    date_range_start: str | None = None  # ISO-8601 date string or None
    date_range_end: str | None = None  # ISO-8601 date string or None


class IntentResult(BaseModel):
    """Strict output of intent classification.

    ``category`` is exactly one of the four FR-002 AnalystCategory values OR
    the literal string ``"unsupported"``.  Nothing else may appear here.
    The turn service checks this and only calls retrieval.py when the category
    is a supported one.
    """

    model_config = ConfigDict(extra="forbid")

    category: AnalystCategory | Literal["unsupported"]
    entities: IntentEntities = Field(default_factory=IntentEntities)


class PriorTurnContext(BaseModel):
    """The immediately preceding turn's resolved category+entities (FR-008).

    Passed into classify() for follow-up turns so the provider can resolve
    omitted entities from context without asking the member to repeat themselves.
    The full resolution logic is wired in US3 (T028); this interface is stable
    from T012 onward so that phase does not need to change the signature.
    """

    model_config = ConfigDict(extra="ignore")

    category: AnalystCategory | Literal["unsupported"]
    entities: IntentEntities = Field(default_factory=IntentEntities)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class IntentProvider(Protocol):
    """Duck-typed interface for intent classification providers."""

    method: str
    model_version: str

    def classify(
        self,
        *,
        question: str,
        prior_turn_context: PriorTurnContext | None = None,
    ) -> IntentResult: ...


# ---------------------------------------------------------------------------
# Real Bedrock-backed provider
# ---------------------------------------------------------------------------

_INTENT_PROMPT = """\
You are a procurement question classifier. Classify the user's question into exactly one \
of these categories, or "unsupported" if it does not fit any of them:

- spend_savings        : questions about spend totals, savings, cost by supplier/product/date
- supplier_performance_risk : questions about supplier risk scores, scorecards, reliability
- orders_quotations    : questions about purchase order status, quotation lines, history
- reorder_forecasts    : questions about reorder proposals, stock forecasts, inventory alerts

If the question falls outside these four categories, classify it as "unsupported".

{prior_context_block}

Return a JSON object with exactly this schema — no markdown fences, no commentary:
{{
  "category": "<one of the four categories above, or \\"unsupported\\">",
  "entities": {{
    "supplier_id": "<UUID string if a specific supplier is mentioned, or null>",
    "product_id": "<UUID string if a specific product is mentioned, or null>",
    "date_range_start": "<ISO-8601 date YYYY-MM-DD if a start date is mentioned, or null>",
    "date_range_end": "<ISO-8601 date YYYY-MM-DD if an end date is mentioned, or null>"
  }}
}}

User question: {question}
"""


class BedrockIntentProvider:
    """Real intent classifier backed by AWS Bedrock/Claude (ADR-004/ADR-014).

    Uses the same boto3 ``client.converse`` call shape as the extraction worker's
    ``BedrockExtractionProvider``.  AWS settings (region, profile, model_id) follow
    the same environment-variable conventions as the extraction worker's own
    ``get_settings()`` (see ``services/extraction-worker/...settings.py``).
    """

    method = "bedrock"

    def __init__(self) -> None:
        self.model_version = os.environ.get(
            "BEDROCK_MODEL_ID",
            "arn:aws:bedrock:us-east-1:524256002093:inference-profile/"
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        self._aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self._aws_profile = os.environ.get("AWS_PROFILE", "")

    def classify(
        self,
        *,
        question: str,
        prior_turn_context: PriorTurnContext | None = None,
    ) -> IntentResult:
        prior_block = ""
        if prior_turn_context is not None:
            prior_block = (
                f"Prior turn context (use to resolve omitted entities in follow-ups): "
                f"category={prior_turn_context.category}, "
                f"entities={prior_turn_context.entities.model_dump(exclude_none=True)}\n\n"
            )

        prompt = _INTENT_PROMPT.format(
            prior_context_block=prior_block,
            question=question,
        )

        session_kwargs: dict[str, Any] = {}
        if self._aws_profile:
            session_kwargs["profile_name"] = self._aws_profile
        try:
            import boto3  # noqa: PLC0415 — lazy: boto3 not in API project deps
        except ModuleNotFoundError as exc:
            raise IntentProviderError(
                "boto3 is not installed. "
                "Set ANALYST_INTENT_PROVIDER_MODE=stub for local/test use."
            ) from exc
        session = boto3.Session(**session_kwargs)
        client = session.client("bedrock-runtime", region_name=self._aws_region)

        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ]

        try:
            response = client.converse(
                modelId=self.model_version,
                messages=messages,
                inferenceConfig={"maxTokens": 512},
            )
        except Exception as exc:
            raise IntentProviderError(f"Bedrock converse failed: {exc}") from exc

        output = response["output"]["message"]["content"]
        text = ""
        for block in output:
            if "text" in block:
                text += block["text"]

        return _parse_intent_response(text)


# ---------------------------------------------------------------------------
# Fake / stub provider (ANALYST_INTENT_PROVIDER_MODE=stub)
# ---------------------------------------------------------------------------

_UNSUPPORTED_KEYWORDS = frozenset(
    [
        "weather",
        "stock market",
        "holiday",
        "joke",
        "news",
        "recipe",
        "sports",
        "travel",
        "entertainment",
        "general knowledge",
    ]
)

_CATEGORY_KEYWORDS: list[tuple[AnalystCategory, frozenset[str]]] = [
    (
        AnalystCategory.spend_savings,
        frozenset(["spend", "spent", "savings", "cost", "saving", "expenditure", "budget"]),
    ),
    (
        AnalystCategory.supplier_performance_risk,
        frozenset(["supplier", "risk", "scorecard", "performance", "reliability", "score"]),
    ),
    (
        # reorder_forecasts must come before orders_quotations so "reorder" doesn't
        # get swallowed by the generic "order" keyword
        AnalystCategory.reorder_forecasts,
        frozenset(["reorder", "forecast", "stock", "inventory", "replenish", "low stock"]),
    ),
    (
        AnalystCategory.orders_quotations,
        frozenset(["quotation", "quote", "purchase order", "status", "po "]),
    ),
]


class FakeIntentProvider:
    """Deterministic offline provider for tests (ANALYST_INTENT_PROVIDER_MODE=stub).

    Explicitly selected, never a fallback.  Classifies by simple keyword matching
    so tests are fully deterministic and make no network calls.  The fake's output
    is stable — tests that encode its fixed classifications must not drift.
    """

    method = "bedrock"
    model_version = "stub-intent-v1"

    def classify(
        self,
        *,
        question: str,
        prior_turn_context: PriorTurnContext | None = None,
    ) -> IntentResult:
        lower = question.lower()

        # Explicit unsupported check first — a keyword of its own always wins, even
        # inside a follow-up: a follow-up with its own subject is a fresh question,
        # not a continuation (FR-008).
        if any(kw in lower for kw in _UNSUPPORTED_KEYWORDS):
            return IntentResult(category="unsupported", entities=IntentEntities())

        for category, keywords in _CATEGORY_KEYWORDS:
            if any(kw in lower for kw in keywords):
                return IntentResult(category=category, entities=IntentEntities())

        # No keyword of its own. If this is a follow-up with usable prior-turn
        # context, resolve the omitted subject from the immediately preceding turn
        # only (FR-008) — never the full conversation history.
        if prior_turn_context is not None and prior_turn_context.category != "unsupported":
            return IntentResult(
                category=prior_turn_context.category,
                entities=prior_turn_context.entities,
            )

        # No keyword and no usable prior context — fall back to unsupported, never guess.
        return IntentResult(category="unsupported", entities=IntentEntities())


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


class IntentProviderError(RuntimeError):
    """Raised when the intent provider call fails."""


def _parse_intent_response(raw: str) -> IntentResult:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntentProviderError(f"Invalid JSON from intent provider: {exc}") from exc
    return IntentResult.model_validate(data)


def get_intent_provider() -> IntentProvider:
    """Return the configured intent provider.

    ANALYST_INTENT_PROVIDER_MODE=stub (default in tests/CI) → FakeIntentProvider.
    ANALYST_INTENT_PROVIDER_MODE=bedrock → BedrockIntentProvider.
    Mirrors EXTRACTION_PROVIDER_MODE's own convention exactly.
    """
    mode = os.environ.get("ANALYST_INTENT_PROVIDER_MODE", "stub")
    if mode == "bedrock":
        return BedrockIntentProvider()
    return FakeIntentProvider()
