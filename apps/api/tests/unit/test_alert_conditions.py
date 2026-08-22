from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.alerts.conditions import _expiring_alerts
from procurepilot_api.modules.alerts.fingerprints import alert_fingerprint
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.schemas import (
    Money,
    Offer,
    ProductRef,
    Recommendation,
    RecommendationEvidence,
)


def test_expiring_alert_condition_uses_current_offer_evidence_and_recurrence_key() -> None:
    now = datetime.now(UTC)
    tenant_id = uuid4()
    product_id = uuid4()
    supplier_id = uuid4()
    offer = Offer(
        id=uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        supplier_name="Fresh Supplier",
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        landed_cost=Money(amount="10.0000", currency="GBP"),
        normalised_unit_price=Money(amount="0.3333", currency="GBP"),
        requested_quantity="1.000000",
        base_unit="litre",
        match_confidence="0.9500",
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=2),
        is_expired=False,
        rule_version="landed-cost-v1",
        recorded_at=now,
    )
    recommendation = Recommendation(
        recommended_offer_id=offer.id,
        score="0.9500",
        confidence="high",
        valid_from=offer.valid_from,
        valid_to=offer.valid_to,
        risk_notes=["price_expiring_soon"],
        evidence=RecommendationEvidence(
            weights={"cost": "0.55"},
            components={"cost": "1.0000"},
            winning_margin=None,
            tie_break={"applied": False, "rule": []},
        ),
    )
    compare = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Tomatoes"),
        offers=[offer],
        recommendation=recommendation,
    )
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=tenant_id,
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )

    alerts = _expiring_alerts(member, compare, now)

    expected_id = alert_fingerprint(
        tenant_id=tenant_id,
        kind="recommended_price_expiring",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key=f"{offer.id}:{offer.valid_to.isoformat()}",
    )
    assert [alert.id for alert in alerts] == [expected_id]
    assert alerts[0].evidence["landed_cost_id"] == str(offer.id)


def test_alert_fingerprints_change_when_recurrence_key_changes() -> None:
    tenant_id = uuid4()
    product_id = uuid4()
    supplier_id = uuid4()
    first = alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_swing",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key="landed-cost-a:15.00",
    )
    second = alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_swing",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key="landed-cost-b:15.00",
    )
    assert first != second
