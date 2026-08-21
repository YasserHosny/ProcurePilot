from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from procurepilot_api.modules.offers.schemas import (
    Money,
    Offer,
    OfferComparison,
    OfferList,
    ProductRef,
    Recommendation,
    RecommendationEvidence,
)


def test_offer_and_compare_contract_requires_money_and_recommendation_evidence() -> None:
    offer = Offer(
        id=uuid4(),
        workspace_product_id=uuid4(),
        supplier_id=uuid4(),
        supplier_name="Fresh Supplier",
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        landed_cost=Money(amount="10.0000", currency="GBP"),
        normalised_unit_price=Money(amount="1.0000", currency="GBP"),
        requested_quantity="10.000000",
        base_unit="kg",
        stock_signal=None,
        match_confidence="0.9200",
        valid_from=datetime.now(UTC),
        is_expired=False,
        rule_version="landed-cost-v1",
        recorded_at=datetime.now(UTC),
    )
    recommendation = Recommendation(
        recommended_offer_id=offer.id,
        score="0.9000",
        confidence="high",
        valid_from=offer.valid_from,
        valid_to=None,
        risk_notes=[],
        evidence=RecommendationEvidence(
            weights={
                "cost": "0.55",
                "match_confidence": "0.20",
                "reliability": "0.15",
                "lead_time": "0.10",
            },
            components={"cost": "1.0000"},
            winning_margin=None,
            tie_break={"applied": False, "rule": []},
        ),
    )
    dumped = OfferComparison(
        product=ProductRef(id=offer.workspace_product_id, tenant_name="Tomatoes"),
        requested_quantity="10.000000",
        offers=[offer],
        recommendation=recommendation,
    ).model_dump(mode="json")
    assert dumped["offers"][0]["landed_cost"] == {"amount": "10.0000", "currency": "GBP"}
    assert dumped["recommendation"]["evidence"]["weights"]["cost"] == "0.55"
    assert OfferList(items=[], next_cursor=None).items == []


def test_recommendation_contract_rejects_bare_label_without_evidence() -> None:
    try:
        Recommendation(
            recommended_offer_id=uuid4(),
            score="0.9000",
            confidence="high",
            valid_from=datetime.now(UTC),
            valid_to=None,
            risk_notes=[],
        )
    except ValidationError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("Recommendation accepted a bare label without structured evidence")
