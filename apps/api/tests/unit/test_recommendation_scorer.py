from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from procurepilot_api.modules.offers.recommendation import TIE_BREAK_RULE, WEIGHTS, recommend_offer
from procurepilot_api.modules.offers.schemas import Money, Offer


def offer(
    *,
    amount: str,
    supplier_id: UUID | None = None,
    workspace_product_id: UUID | None = None,
    confidence: str = "0.9200",
    reliability: str | None = "0.900",
    lead_time: int | None = 2,
    valid_to: datetime | None = None,
    supplier_name: str = "Supplier",
    currency: str = "GBP",
) -> Offer:
    return Offer(
        id=uuid4(),
        workspace_product_id=workspace_product_id or uuid4(),
        supplier_id=supplier_id or uuid4(),
        supplier_name=supplier_name,
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        landed_cost=Money(amount=amount, currency=currency),
        normalised_unit_price=Money(amount=amount, currency=currency),
        requested_quantity="1.000000",
        base_unit="kg",
        lead_time_days=lead_time,
        reliability_score=reliability,
        stock_signal=None,
        match_confidence=confidence,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_to=valid_to,
        is_expired=False,
        rule_version="landed-cost-v1",
        recorded_at=datetime.now(UTC),
    )


def test_recommendation_uses_research_r2_weights_thresholds_risks_and_null_neutral_scores() -> None:
    assert WEIGHTS == {
        "cost": "0.55",
        "match_confidence": "0.20",
        "reliability": "0.15",
        "lead_time": "0.10",
    } or {key: format(value, "f") for key, value in WEIGHTS.items()} == {
        "cost": "0.55",
        "match_confidence": "0.20",
        "reliability": "0.15",
        "lead_time": "0.10",
    }
    now = datetime.now(UTC)
    recommendation = recommend_offer(
        [
            offer(
                amount="10.0000",
                confidence="0.8000",
                reliability="0.500",
                lead_time=None,
                valid_to=now + timedelta(days=2),
            ),
            offer(amount="12.0000", reliability=None, lead_time=None),
        ],
        now=now,
    )
    assert recommendation is not None
    assert recommendation.evidence.weights == {
        "cost": "0.55",
        "match_confidence": "0.20",
        "reliability": "0.15",
        "lead_time": "0.10",
    }
    assert recommendation.confidence in {"medium", "low"}
    assert recommendation.risk_notes == [
        "price_expiring_soon",
        "low_match_confidence",
        "low_supplier_reliability",
    ]


def test_recommendation_excludes_non_reference_currency_before_comparing_costs() -> None:
    reference_supplier = UUID("00000000-0000-4000-8000-000000000001")
    other_supplier = UUID("00000000-0000-4000-8000-000000000002")
    product_id = uuid4()
    reference_offer = offer(
        amount="10.0000",
        supplier_id=reference_supplier,
        workspace_product_id=product_id,
        supplier_name="Reference currency",
        currency="GBP",
    )
    other_offer = offer(
        amount="1.0000",
        supplier_id=other_supplier,
        workspace_product_id=product_id,
        supplier_name="Other currency",
        currency="EUR",
    )
    recommendation = recommend_offer(
        [reference_offer, other_offer]
    )

    assert recommendation is not None
    assert recommendation.recommended_offer_id == reference_offer.id
    assert "currency_mismatch_excluded" in recommendation.risk_notes


def test_recommendation_does_not_note_currency_exclusion_for_same_currency_offers() -> None:
    recommendation = recommend_offer([offer(amount="10.0000"), offer(amount="11.0000")])

    assert recommendation is not None
    assert "currency_mismatch_excluded" not in recommendation.risk_notes


def test_sc006_honest_gap_has_no_ml_eval_until_outcome_history_exists() -> None:
    """Chunk 4.5 can test deterministic scoring, not acceptance quality.

    There is no buyer decision/outcome history until chunk 4.6, so a synthetic ml/evals harness
    would produce a misleading acceptance claim instead of measuring SC-006 honestly.
    """

    assert "lexicographic_supplier_id" in TIE_BREAK_RULE


def test_recommendation_can_include_supplier_iq_risk_evidence_when_available() -> None:
    risky_supplier = offer(amount="10.0000", supplier_name="Risky Supplier")
    safer_supplier = offer(amount="10.5000", supplier_name="Safer Supplier")

    recommendation = recommend_offer(
        [risky_supplier, safer_supplier],
        supplier_risk_scores={
            risky_supplier.supplier_id: "0.9000",
            safer_supplier.supplier_id: "0.1000",
        },
    )

    assert recommendation is not None
    assert recommendation.recommended_offer_id == safer_supplier.id
    assert recommendation.evidence.weights["supplier_risk"] == "0.15"
    total_weight = sum(Decimal(weight) for weight in recommendation.evidence.weights.values())
    assert total_weight == Decimal("1.00")
    assert recommendation.evidence.components["supplier_risk"] == "0.1000"
    assert "high_supplier_risk" not in recommendation.risk_notes


def test_recommendation_notes_high_supplier_risk_for_winning_supplier() -> None:
    risky_supplier = offer(amount="10.0000", supplier_name="Risky Supplier")

    recommendation = recommend_offer(
        [risky_supplier],
        supplier_risk_scores={risky_supplier.supplier_id: "0.9000"},
    )

    assert recommendation is not None
    assert recommendation.recommended_offer_id == risky_supplier.id
    assert recommendation.evidence.components["supplier_risk"] == "0.9000"
    assert "high_supplier_risk" in recommendation.risk_notes
