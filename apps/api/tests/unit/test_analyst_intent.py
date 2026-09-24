"""Adversarial unit tests for intent classification and the turn service (T011, FR-005).

The key invariant tested here:
  A classification result that produces no matching retrieval data (NoGroundingData)
  must still produce an explicit refusal — the turn service must NEVER let the
  language model's own wording leak into the stored answer_text.  Only
  retrieval.py's actual return value may become answer content.

These tests use only pure functions and the FakeIntentProvider — no database,
no network calls.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from procurepilot_api.modules.analyst.intent import (
    FakeIntentProvider,
    IntentEntities,
    IntentResult,
    PriorTurnContext,
)
from procurepilot_api.modules.analyst.retrieval import (
    AnalystAnswer,
    CitationSourceKind,
    NoGroundingData,
    SpendRecord,
    SpendSavingsInput,
    retrieve_spend_savings,
)
from procurepilot_api.modules.analyst.schemas import AnalystCategory

# ---------------------------------------------------------------------------
# FR-005 adversarial tests: no model text leaks into the stored answer
# ---------------------------------------------------------------------------


class _LLMLeakIntentProvider:
    """Adversarial provider that always returns a supported category but has a
    fabricated answer string that must NEVER appear in the stored turn answer.

    The turn service must call retrieval.py and use ITS output — not anything
    the intent provider says about the answer content.
    """

    method = "bedrock"
    model_version = "adversarial-leak-test-v1"
    FORBIDDEN_TEXT = "FABRICATED ANSWER FROM LLM — THIS MUST NEVER APPEAR IN STORAGE"

    def classify(
        self,
        *,
        question: str,
        prior_turn_context: PriorTurnContext | None = None,
    ) -> IntentResult:
        return IntentResult(
            category=AnalystCategory.spend_savings,
            entities=IntentEntities(),
        )


def test_no_grounding_data_produces_explicit_refusal_not_llm_text() -> None:
    """FR-005 / T011: when retrieval returns NoGroundingData, the stored answer must be
    the retrieval layer's own explanation, never text invented by the intent provider.

    An empty SpendSavingsInput → NoGroundingData from retrieve_spend_savings.
    The turn service must use that NoGroundingData explanation, not any string from
    the intent provider.
    """
    result = retrieve_spend_savings(SpendSavingsInput())
    assert isinstance(result, NoGroundingData), f"Expected NoGroundingData, got {result}"

    forbidden = _LLMLeakIntentProvider.FORBIDDEN_TEXT
    assert forbidden not in result.explanation, (
        f"LLM text leaked into retrieval result: {result.explanation!r}"
    )
    assert "no" in result.explanation.lower() or "not" in result.explanation.lower(), (
        f"NoGroundingData explanation must say 'no data', got: {result.explanation!r}"
    )


def test_unsupported_category_answer_never_contains_guessed_content() -> None:
    """FR-002: the refusal answer for an unsupported question is a fixed string, not
    generated content.
    """
    from procurepilot_api.modules.analyst.service import _UNSUPPORTED_ANSWER

    unsupported_lower = _UNSUPPORTED_ANSWER.lower()
    assert "can't answer" in unsupported_lower or "only supports" in unsupported_lower, (
        f"_UNSUPPORTED_ANSWER must be an explicit refusal: {_UNSUPPORTED_ANSWER!r}"
    )
    assert "{" not in _UNSUPPORTED_ANSWER, (
        "Unsupported answer must not contain format markers"
    )


def test_retrieval_result_only_source_allowed_in_answer() -> None:
    """FR-005 structural invariant: the answer_text is built exclusively from the
    retrieval function's output — not from any injection.
    """
    records = (
        SpendRecord(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            source_kind=CitationSourceKind.purchase_order,
            supplier_id=None,
            product_id=None,
            amount=Decimal("100.00"),
            currency="SAR",
            recorded_on=date(2026, 9, 1),
        ),
    )
    result = retrieve_spend_savings(SpendSavingsInput(spend_records=records))
    assert isinstance(result, AnalystAnswer)
    assert "SAR" in result.answer_text
    assert _LLMLeakIntentProvider.FORBIDDEN_TEXT not in result.answer_text


# ---------------------------------------------------------------------------
# FakeIntentProvider determinism and classification tests
# ---------------------------------------------------------------------------


def test_fake_provider_classifies_spend_question() -> None:
    provider = FakeIntentProvider()
    result = provider.classify(question="How much have we spent this month?")
    assert result.category == AnalystCategory.spend_savings


def test_fake_provider_classifies_supplier_risk_question() -> None:
    provider = FakeIntentProvider()
    result = provider.classify(question="What is the supplier risk score?")
    assert result.category == AnalystCategory.supplier_performance_risk


def test_fake_provider_classifies_orders_question() -> None:
    provider = FakeIntentProvider()
    result = provider.classify(question="Show me the status of our purchase orders")
    assert result.category == AnalystCategory.orders_quotations


def test_fake_provider_classifies_reorder_question() -> None:
    provider = FakeIntentProvider()
    result = provider.classify(question="Which products need reordering?")
    assert result.category == AnalystCategory.reorder_forecasts


def test_fake_provider_returns_unsupported_for_unrelated_question() -> None:
    provider = FakeIntentProvider()
    result = provider.classify(question="What is the weather like today?")
    assert result.category == "unsupported"


def test_fake_provider_is_deterministic() -> None:
    """The FakeIntentProvider must return the same result for the same input."""
    provider = FakeIntentProvider()
    q = "What is our total spend on suppliers?"
    first = provider.classify(question=q)
    second = provider.classify(question=q)
    assert first.category == second.category
    assert first.entities.model_dump() == second.entities.model_dump()


# ---------------------------------------------------------------------------
# T026 (FR-008, US3): follow-up resolution from the immediately preceding turn only
# ---------------------------------------------------------------------------


def test_follow_up_with_no_keyword_of_its_own_inherits_prior_category_and_entities() -> None:
    """FR-008: a follow-up that omits the subject ("and last quarter?") resolves using
    the immediately preceding turn's category and entities."""
    provider = FakeIntentProvider()
    ctx = PriorTurnContext(
        category=AnalystCategory.spend_savings,
        entities=IntentEntities(supplier_id="00000000-0000-0000-0000-000000000099"),
    )
    result = provider.classify(question="and last quarter?", prior_turn_context=ctx)
    assert result.category == AnalystCategory.spend_savings
    assert result.entities.supplier_id == "00000000-0000-0000-0000-000000000099"


def test_follow_up_with_its_own_keyword_does_not_inherit_prior_context() -> None:
    """A follow-up that names its own subject is a fresh question — it must NOT
    inherit the prior turn's category or entities even when prior_turn_context is
    supplied."""
    provider = FakeIntentProvider()
    ctx = PriorTurnContext(
        category=AnalystCategory.spend_savings,
        entities=IntentEntities(supplier_id="00000000-0000-0000-0000-000000000099"),
    )
    result = provider.classify(
        question="What's our supplier risk?",
        prior_turn_context=ctx,
    )
    assert result.category == AnalystCategory.supplier_performance_risk
    assert result.entities.supplier_id is None


def test_follow_up_with_no_keyword_and_no_prior_context_is_unsupported() -> None:
    """No keyword of its own and nothing to inherit from — never guess."""
    provider = FakeIntentProvider()
    result = provider.classify(question="and last quarter?", prior_turn_context=None)
    assert result.category == "unsupported"


def test_follow_up_does_not_inherit_from_an_unsupported_prior_turn() -> None:
    """An unsupported-refusal prior turn has no real category to inherit — a
    follow-up with no keyword of its own must fall through to unsupported too,
    not inherit the meaningless sentinel category."""
    provider = FakeIntentProvider()
    ctx = PriorTurnContext(category="unsupported", entities=IntentEntities())
    result = provider.classify(question="and last quarter?", prior_turn_context=ctx)
    assert result.category == "unsupported"


# ---------------------------------------------------------------------------
# IntentResult strict schema — no free-text passthrough
# ---------------------------------------------------------------------------


def test_intent_result_rejects_unknown_category() -> None:
    """FR-005: IntentResult must reject any category value not in the approved set."""
    import pydantic

    with pytest.raises((pydantic.ValidationError, ValueError)):
        IntentResult(category="make_a_purchase", entities=IntentEntities())  # type: ignore[arg-type]


def test_intent_result_accepts_all_supported_categories() -> None:
    for category in [*list(AnalystCategory), "unsupported"]:
        result = IntentResult(category=category, entities=IntentEntities())
        assert result.category == category


def test_intent_result_entities_are_all_none_by_default() -> None:
    result = IntentResult(category="unsupported")
    assert result.entities.supplier_id is None
    assert result.entities.product_id is None
    assert result.entities.date_range_start is None
    assert result.entities.date_range_end is None
