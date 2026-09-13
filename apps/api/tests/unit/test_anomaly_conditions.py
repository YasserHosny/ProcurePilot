from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.alerts.conditions import (
    _decimal_anomaly_alerts,
    _delivery_cost_alerts,
    _duplicate_line_alerts,
    _price_spike_alerts,
    _supplier_quality_alerts,
)
from procurepilot_api.modules.alerts.fingerprints import (
    alert_fingerprint,
    decimal_anomaly_recurrence_key,
    delivery_cost_recurrence_key,
    duplicate_line_recurrence_key,
    price_spike_recurrence_key,
    supplier_quality_recurrence_key,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.schemas import (
    Money,
    Offer,
    PriceHistoryMetric,
    PriceHistoryResponse,
    PriceHistorySummary,
    ProductRef,
    Recommendation,
    RecommendationEvidence,
)


def _make_member() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def _make_offer(
    *,
    product_id: uuid4,
    supplier_id: uuid4,
    amount: str = "10.0000",
    quantity: str = "1.000000",
    line_id: uuid4 | None = None,
    offer_id: uuid4 | None = None,
    valid_to: datetime | None = None,
) -> Offer:
    now = datetime.now(UTC)
    return Offer(
        id=offer_id or uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        supplier_name="Acme Supplies",
        quotation_line_id=line_id or uuid4(),
        match_decision_id=uuid4(),
        landed_cost=Money(amount=amount, currency="GBP"),
        normalised_unit_price=Money(amount=amount, currency="GBP"),
        requested_quantity=quantity,
        base_unit="piece",
        match_confidence="0.9500",
        valid_from=now - timedelta(days=1),
        valid_to=valid_to or (now + timedelta(days=10)),
        is_expired=False,
        rule_version="landed-cost-v1",
        recorded_at=now,
    )


def test_price_spike_detection_and_severity() -> None:
    now = datetime.now(UTC)
    member = _make_member()
    product_id = uuid4()
    supplier_id = uuid4()

    # Case 1: Spike of 25% (warning, medium confidence with 2 samples)
    offer_25 = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="12.5000")
    compare_25 = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Sugar"),
        offers=[offer_25],
        recommendation=Recommendation(
            recommended_offer_id=offer_25.id,
            score="0.9",
            confidence="high",
            valid_from=offer_25.valid_from,
            valid_to=offer_25.valid_to,
            risk_notes=[],
            evidence=RecommendationEvidence(
                weights={},
                components={},
                winning_margin=None,
                tie_break={"applied": False, "rule": []},
            ),
        ),
    )

    history_2 = PriceHistoryResponse(
        product=compare_25.product,
        window_months=6,
        points=[],
        summary=PriceHistorySummary(
            average_paid_rolling_window=PriceHistoryMetric(
                value=Money(amount="10.0000", currency="GBP"),
                source_landed_cost_ids=[uuid4(), uuid4()],
            ),
            last_paid=None,
            best_price=None,
        ),
    )
    offers_service = SimpleNamespace(price_history=lambda **_: history_2)

    alerts = _price_spike_alerts(offers_service, member, compare_25, now)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kind == "price_spike"
    assert alert.severity == "warning"
    assert alert.confidence == "medium"
    assert alert.action == "view_price_history"
    assert alert.evidence["spike_percentage"] == "25.00"
    expected_fingerprint = alert_fingerprint(
        tenant_id=member.tenant_id,
        kind="price_spike",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key=price_spike_recurrence_key(offer_25.id, "25.00"),
    )
    assert alert.id == expected_fingerprint

    # Case 2: Spike of 40% (critical, high confidence with 5 samples)
    offer_40 = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="14.0000")
    compare_40 = SimpleNamespace(
        product=compare_25.product,
        offers=[offer_40],
        recommendation=Recommendation(
            recommended_offer_id=offer_40.id,
            score="0.9",
            confidence="high",
            valid_from=offer_40.valid_from,
            valid_to=offer_40.valid_to,
            risk_notes=[],
            evidence=RecommendationEvidence(
                weights={},
                components={},
                winning_margin=None,
                tie_break={"applied": False, "rule": []},
            ),
        ),
    )
    history_5 = PriceHistoryResponse(
        product=compare_25.product,
        window_months=6,
        points=[],
        summary=PriceHistorySummary(
            average_paid_rolling_window=PriceHistoryMetric(
                value=Money(amount="10.0000", currency="GBP"),
                source_landed_cost_ids=[uuid4() for _ in range(5)],
            ),
            last_paid=None,
            best_price=None,
        ),
    )
    offers_service_5 = SimpleNamespace(price_history=lambda **_: history_5)
    alerts_40 = _price_spike_alerts(offers_service_5, member, compare_40, now)
    assert len(alerts_40) == 1
    assert alerts_40[0].severity == "critical"
    assert alerts_40[0].confidence == "high"

    # Case 3: Below threshold (+10%) -> no alert
    offer_10 = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="11.0000")
    compare_10 = SimpleNamespace(
        product=compare_25.product,
        offers=[offer_10],
        recommendation=Recommendation(
            recommended_offer_id=offer_10.id,
            score="0.9",
            confidence="high",
            valid_from=offer_10.valid_from,
            valid_to=offer_10.valid_to,
            risk_notes=[],
            evidence=RecommendationEvidence(
                weights={},
                components={},
                winning_margin=None,
                tie_break={"applied": False, "rule": []},
            ),
        ),
    )
    alerts_10 = _price_spike_alerts(offers_service_5, member, compare_10, now)
    assert len(alerts_10) == 0


def test_likely_duplicate_quotation_line_detection() -> None:
    now = datetime.now(UTC)
    member = _make_member()
    product_id = uuid4()
    supplier_id = uuid4()
    line_1 = uuid4()
    line_2 = uuid4()

    # Same supplier, identical price and quantity
    offer_1 = _make_offer(
        product_id=product_id,
        supplier_id=supplier_id,
        amount="5.5000",
        quantity="10.000000",
        line_id=line_1,
    )
    offer_2 = _make_offer(
        product_id=product_id,
        supplier_id=supplier_id,
        amount="5.5000",
        quantity="10.000000",
        line_id=line_2,
    )
    compare = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Flour"),
        offers=[offer_1, offer_2],
    )

    alerts = _duplicate_line_alerts(member, compare, now)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kind == "likely_duplicate_quotation_line"
    assert alert.severity == "warning"
    assert alert.confidence == "high"
    assert alert.action == "review_quotation"
    assert alert.evidence["requested_quantity_1"] == "10.000000"
    expected_fingerprint = alert_fingerprint(
        tenant_id=member.tenant_id,
        kind="likely_duplicate_quotation_line",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key=duplicate_line_recurrence_key(line_1, line_2),
    )
    assert alert.id == expected_fingerprint

    # Different supplier with same price -> not a duplicate
    other_supplier_id = uuid4()
    offer_3 = _make_offer(
        product_id=product_id,
        supplier_id=other_supplier_id,
        amount="5.5000",
        quantity="10.000000",
    )
    compare_diff = SimpleNamespace(
        product=compare.product,
        offers=[offer_1, offer_3],
    )
    alerts_diff = _duplicate_line_alerts(member, compare_diff, now)
    assert len(alerts_diff) == 0


def test_decimal_or_quantity_anomaly_detection() -> None:
    now = datetime.now(UTC)
    member = _make_member()
    product_id = uuid4()
    supplier_id = uuid4()

    # Case 1: 10x magnitude spike (critical, action review_quotation)
    offer_spike = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="100.0000")
    compare_spike = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Olive Oil"),
        offers=[offer_spike],
    )
    history_baseline = PriceHistoryResponse(
        product=compare_spike.product,
        window_months=6,
        points=[],
        summary=PriceHistorySummary(
            average_paid_rolling_window=PriceHistoryMetric(
                value=Money(amount="10.0000", currency="GBP"),
                source_landed_cost_ids=[uuid4(), uuid4(), uuid4()],
            ),
            last_paid=None,
            best_price=None,
        ),
    )
    offers_service = SimpleNamespace(price_history=lambda **_: history_baseline)

    alerts_spike = _decimal_anomaly_alerts(offers_service, member, compare_spike, now)
    assert len(alerts_spike) == 1
    assert alerts_spike[0].kind == "decimal_or_quantity_anomaly"
    assert alerts_spike[0].severity == "critical"
    assert alerts_spike[0].confidence == "high"
    assert alerts_spike[0].action == "review_quotation"
    assert alerts_spike[0].evidence["anomaly_type"] == "magnitude_spike"
    assert alerts_spike[0].evidence["ratio"] == "10.0000"

    # Case 2: 0.1x magnitude drop (warning, action review_quotation)
    offer_drop = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="1.0000")
    compare_drop = SimpleNamespace(
        product=compare_spike.product,
        offers=[offer_drop],
    )
    alerts_drop = _decimal_anomaly_alerts(offers_service, member, compare_drop, now)
    assert len(alerts_drop) == 1
    assert alerts_drop[0].severity == "warning"
    assert alerts_drop[0].evidence["anomaly_type"] == "magnitude_drop"
    assert alerts_drop[0].evidence["ratio"] == "0.1000"

    # Case 3: Normal fluctuation (1.5x) -> no alert
    offer_normal = _make_offer(product_id=product_id, supplier_id=supplier_id, amount="15.0000")
    compare_normal = SimpleNamespace(
        product=compare_spike.product,
        offers=[offer_normal],
    )
    alerts_normal = _decimal_anomaly_alerts(offers_service, member, compare_normal, now)
    assert len(alerts_normal) == 0


def test_delivery_cost_anomaly_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    member = _make_member()
    product_id = uuid4()
    supplier_id = uuid4()
    offer = _make_offer(product_id=product_id, supplier_id=supplier_id)
    compare = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Salt"),
        offers=[offer],
    )

    # 45% of MOV -> warning
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._latest_supplier_commercial_term",
        lambda *_, **__: {
            "delivery_fee_amount": "45.0000",
            "minimum_order_value_amount": "100.0000",
            "delivery_fee_currency": "GBP",
        },
    )
    alerts = _delivery_cost_alerts(None, member, compare, now)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kind == "delivery_cost_anomaly"
    assert alert.severity == "warning"
    assert alert.confidence == "high"
    assert alert.action == "view_delivery_issues"
    assert alert.evidence["delivery_fee"] == "45.00"
    assert alert.evidence["fee_ratio"] == "0.4500"

    # 75% of MOV -> critical
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._latest_supplier_commercial_term",
        lambda *_, **__: {
            "delivery_fee_amount": "75.0000",
            "minimum_order_value_amount": "100.0000",
            "delivery_fee_currency": "GBP",
        },
    )
    alerts_crit = _delivery_cost_alerts(None, member, compare, now)
    assert len(alerts_crit) == 1
    assert alerts_crit[0].severity == "critical"

    # 20% of MOV -> normal, no anomaly
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._latest_supplier_commercial_term",
        lambda *_, **__: {
            "delivery_fee_amount": "20.0000",
            "minimum_order_value_amount": "100.0000",
            "delivery_fee_currency": "GBP",
        },
    )
    alerts_norm = _delivery_cost_alerts(None, member, compare, now)
    assert len(alerts_norm) == 0


def test_supplier_quality_trend_change_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    member = _make_member()
    product_id = uuid4()
    supplier_id = uuid4()
    offer = _make_offer(product_id=product_id, supplier_id=supplier_id)
    compare = SimpleNamespace(
        product=ProductRef(id=product_id, tenant_name="Milk"),
        offers=[offer],
    )

    # Dispute rate 12%, quality score 0.65 -> critical, high confidence
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._get_supplier_quality_stats",
        lambda *_, **__: (Decimal("0.1200"), Decimal("0.6500"), 3, 15),
    )
    alerts_crit = _supplier_quality_alerts(None, member, compare, now)
    assert len(alerts_crit) == 1
    alert = alerts_crit[0]
    assert alert.kind == "supplier_quality_trend_change"
    assert alert.severity == "critical"
    assert alert.confidence == "high"
    assert alert.action == "inspect_scorecard"
    assert alert.evidence["dispute_rate"] == "0.1200"
    assert alert.evidence["quality_score"] == "0.6500"

    # Dispute rate 6%, quality score 0.82 -> warning, medium confidence
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._get_supplier_quality_stats",
        lambda *_, **__: (Decimal("0.0600"), Decimal("0.8200"), 1, 5),
    )
    alerts_warn = _supplier_quality_alerts(None, member, compare, now)
    assert len(alerts_warn) == 1
    assert alerts_warn[0].severity == "warning"
    assert alerts_warn[0].confidence == "medium"

    # Clean stats: dispute rate 0, quality score 1.0, 0 issues -> no anomaly
    monkeypatch.setattr(
        "procurepilot_api.modules.alerts.conditions._get_supplier_quality_stats",
        lambda *_, **__: (Decimal("0.0000"), Decimal("1.0000"), 0, 10),
    )
    alerts_clean = _supplier_quality_alerts(None, member, compare, now)
    assert len(alerts_clean) == 0


def test_anomaly_recurrence_keys_deterministic_and_unique() -> None:
    tenant_id = uuid4()
    product_id = uuid4()
    supplier_id = uuid4()
    lc1 = uuid4()

    # Price spike recurrence key changes when percentage changes
    k1 = price_spike_recurrence_key(lc1, "25.00")
    k2 = price_spike_recurrence_key(lc1, "30.00")
    assert k1 != k2
    assert alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_spike",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key=k1,
    ) != alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_spike",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key=k2,
    )

    # Duplicate line key is order-independent
    line_a = uuid4()
    line_b = uuid4()
    assert duplicate_line_recurrence_key(line_a, line_b) == duplicate_line_recurrence_key(
        line_b, line_a
    )

    # Decimal anomaly recurrence key
    d1 = decimal_anomaly_recurrence_key(lc1, "10.0000")
    d2 = decimal_anomaly_recurrence_key(lc1, "0.1000")
    assert d1 != d2

    # Delivery cost recurrence key
    dc1 = delivery_cost_recurrence_key(supplier_id, "45.00")
    dc2 = delivery_cost_recurrence_key(supplier_id, "50.00")
    assert dc1 != dc2

    # Supplier quality recurrence key
    sq1 = supplier_quality_recurrence_key(supplier_id, "0.0500", "0.8000", 2)
    sq2 = supplier_quality_recurrence_key(supplier_id, "0.1000", "0.7000", 3)
    assert sq1 != sq2
