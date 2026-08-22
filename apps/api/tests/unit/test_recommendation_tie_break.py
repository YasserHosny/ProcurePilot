from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from procurepilot_api.modules.offers.recommendation import TIE_BREAK_RULE, recommend_offer
from procurepilot_api.modules.offers.schemas import Money, Offer


def _offer(
    *,
    supplier_id: UUID,
    supplier_name: str,
    amount: str,
    confidence: str,
    reliability: str | None,
    lead_time: int | None,
    valid_to: datetime | None,
) -> Offer:
    return Offer(
        id=uuid4(),
        workspace_product_id=uuid4(),
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        landed_cost=Money(amount=amount, currency="GBP"),
        normalised_unit_price=Money(amount=amount, currency="GBP"),
        requested_quantity="1.000000",
        base_unit="kg",
        lead_time_days=lead_time,
        reliability_score=reliability,
        stock_signal=None,
        match_confidence=confidence,
        valid_from=datetime.now(UTC),
        valid_to=valid_to,
        is_expired=False,
        rule_version="landed-cost-v1",
        recorded_at=datetime.now(UTC),
    )


def test_tie_break_uses_research_r3_seven_step_rule_and_exposes_evidence() -> None:
    supplier_a = UUID("00000000-0000-4000-8000-000000000001")
    supplier_b = UUID("00000000-0000-4000-8000-000000000002")
    now = datetime.now(UTC)
    recommendation = recommend_offer(
        [
            _offer(
                supplier_id=supplier_b,
                supplier_name="Beta",
                amount="10.0000",
                confidence="0.9000",
                reliability="0.900",
                lead_time=5,
                valid_to=now + timedelta(days=3),
            ),
            _offer(
                supplier_id=supplier_a,
                supplier_name="Alpha",
                amount="10.0000",
                confidence="0.9000",
                reliability="0.900",
                lead_time=5,
                valid_to=now + timedelta(days=3),
            ),
        ],
        now=now,
    )
    assert recommendation is not None
    assert recommendation.evidence.tie_break["applied"] is True
    assert recommendation.evidence.tie_break["rule"] == TIE_BREAK_RULE
    assert recommendation.evidence.tie_break["winner_supplier_id"] == str(supplier_a)
