from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.rfq.guardrails import (
    AutoPreparationGuardrail,
    GuardrailCandidate,
    GuardrailCandidateLine,
    GuardrailEvaluationInput,
    evaluate_guardrail,
)


@pytest.fixture
def base_guardrail() -> AutoPreparationGuardrail:
    return AutoPreparationGuardrail(
        id=uuid4(),
        tenant_id=uuid4(),
        enabled=True,
        min_response_count=1,
        max_order_value_amount=Decimal("1000.00"),
        max_order_value_currency="USD",
        max_price_variance_pct=Decimal("0.10"),
        supplier_allowlist=None,
        category_allowlist=None,
        default_branch_id=uuid4(),
        created_by_membership_id=uuid4(),
    )


@pytest.fixture
def product_id() -> UUID:
    return uuid4()


@pytest.fixture
def supplier_id() -> UUID:
    return uuid4()


@pytest.fixture
def base_candidate(supplier_id: UUID, product_id: UUID) -> GuardrailCandidate:
    return GuardrailCandidate(
        rfq_response_id=uuid4(),
        supplier_id=supplier_id,
        currency="USD",
        total_amount=Decimal("500.00"),
        all_lines_matched=True,
        matched_lines=[
            GuardrailCandidateLine(
                workspace_product_id=product_id, unit_price_amount=Decimal("100.00")
            )
        ],
    )


def test_guardrail_disabled(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_guardrail.enabled = False
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "guardrail_disabled"


def test_rfq_not_open(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="converted",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "rfq_not_open"


def test_min_response_count_not_met(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_guardrail.min_response_count = 3
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=2,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "min_response_count_not_met"


def test_partial_line_response(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_candidate.all_lines_matched = False
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "partial_line_response"


def test_currency_mismatch(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_candidate.currency = "EUR"
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "currency_mismatch"


def test_supplier_not_allowed(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_guardrail.supplier_allowlist = [uuid4()]
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "supplier_not_allowed"


def test_supplier_allowed(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
    supplier_id: UUID,
) -> None:
    base_guardrail.supplier_allowlist = [supplier_id]
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert decision.fired
    assert decision.reason == "guardrail_fired"


def test_category_allowlist_unsupported(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_guardrail.category_allowlist = ["some_category"]
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "category_allowlist_unsupported"


def test_exceeds_max_order_value(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    base_candidate.total_amount = Decimal("2000.00")
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "exceeds_max_order_value"


def test_no_price_history_baseline(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={},
        )
    )
    assert not decision.fired
    assert decision.reason == "no_price_history_baseline"


def test_price_variance_exceeded(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    # Baseline 100, quoted 111 (11% variance) against a 10% max.
    base_candidate.matched_lines[0].unit_price_amount = Decimal("111.00")
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "price_variance_exceeded"


def test_price_variance_ok(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    # Baseline 100, quoted 105 (5% variance) against a 10% max.
    base_candidate.matched_lines[0].unit_price_amount = Decimal("105.00")
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert decision.fired
    assert decision.reason == "guardrail_fired"


def test_multiple_candidates_no_eligible(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    c2 = GuardrailCandidate(
        rfq_response_id=uuid4(),
        supplier_id=uuid4(),
        currency="EUR",
        total_amount=Decimal("500.00"),
        all_lines_matched=True,
        matched_lines=[
            GuardrailCandidateLine(
                workspace_product_id=product_id, unit_price_amount=Decimal("100.00")
            )
        ],
    )
    base_candidate.all_lines_matched = False

    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=2,
            candidates=[base_candidate, c2],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "no_eligible_response"


def test_tied_responses(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    c2 = GuardrailCandidate(
        rfq_response_id=uuid4(),
        supplier_id=uuid4(),
        currency="USD",
        total_amount=Decimal("500.00"),
        all_lines_matched=True,
        matched_lines=[
            GuardrailCandidateLine(
                workspace_product_id=product_id, unit_price_amount=Decimal("100.00")
            )
        ],
    )
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=2,
            candidates=[base_candidate, c2],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert not decision.fired
    assert decision.reason == "tied_responses"


def test_guardrail_fired(
    base_guardrail: AutoPreparationGuardrail,
    base_candidate: GuardrailCandidate,
    product_id: UUID,
) -> None:
    decision = evaluate_guardrail(
        GuardrailEvaluationInput(
            guardrail=base_guardrail,
            rfq_status="sent",
            total_response_count=1,
            candidates=[base_candidate],
            recent_average_price_by_product={product_id: Decimal("100.00")},
        )
    )
    assert decision.fired
    assert decision.reason == "guardrail_fired"
    assert decision.winning_response_id == base_candidate.rfq_response_id
