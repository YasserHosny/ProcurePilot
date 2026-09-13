from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.modules.alerts.service import AlertService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_price_spike_anomaly_live_dismissal_and_recurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("spike-live", supplier_count=1) as context:
        # Seed 2 historical baseline offers at 10.00 GBP
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("10.0000"),
            valid_to=now + timedelta(days=30),
            recorded_at=now - timedelta(days=30),
        )
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("10.0000"),
            valid_to=now + timedelta(days=30),
            recorded_at=now - timedelta(days=20),
        )

        # Current offer at 15.00 GBP (+50% spike)
        current = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("15.0000"),
            valid_to=now + timedelta(days=5),
            recorded_at=now,
        )

        service = AlertService(settings)
        alerts = service.list_alerts(member=context.member, kind="price_spike")
        assert len(alerts.items) == 1
        spike_alert = alerts.items[0]
        assert spike_alert.kind == "price_spike"
        assert spike_alert.severity == "critical"
        assert spike_alert.action == "view_price_history"
        assert spike_alert.evidence["landed_cost_id"] == str(current.landed_cost_id)

        # Dismiss alert
        service.dismiss_alert(member=context.member, alert_id=spike_alert.id)
        after_dismissal = service.list_alerts(member=context.member, kind="price_spike")
        assert spike_alert.id not in {a.id for a in after_dismissal.items}

        # New offer with changed price (16.00 GBP) -> alert recurs with different fingerprint
        recurrent_offer = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("16.0000"),
            valid_to=now + timedelta(days=6),
            recorded_at=now + timedelta(minutes=1),
        )
        after_change = service.list_alerts(member=context.member, kind="price_spike")
        assert len(after_change.items) == 1
        assert after_change.items[0].id != spike_alert.id
        assert after_change.items[0].evidence["landed_cost_id"] == str(
            recurrent_offer.landed_cost_id
        )


def test_likely_duplicate_quotation_line_anomaly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("dup-live", supplier_count=1) as context:
        # Two offers from same supplier with identical price and quantity
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("12.0000"),
            quantity=Decimal("5.000000"),
            valid_to=now + timedelta(days=10),
            recorded_at=now,
        )
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("12.0000"),
            quantity=Decimal("5.000000"),
            valid_to=now + timedelta(days=10),
            recorded_at=now,
        )

        service = AlertService(settings)
        alerts = service.list_alerts(member=context.member, kind="likely_duplicate_quotation_line")
        assert len(alerts.items) >= 1
        dup_alert = next(a for a in alerts.items if a.kind == "likely_duplicate_quotation_line")
        assert dup_alert.severity == "warning"
        assert dup_alert.confidence == "high"
        assert dup_alert.action == "review_quotation"

        # Dismiss duplicate alert
        service.dismiss_alert(member=context.member, alert_id=dup_alert.id)
        after_dismissal = service.list_alerts(
            member=context.member, kind="likely_duplicate_quotation_line"
        )
        assert dup_alert.id not in {a.id for a in after_dismissal.items}


def test_decimal_or_quantity_anomaly_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("decimal-live", supplier_count=1) as context:
        # 3 baseline offers at 10.00 GBP
        for i in range(3):
            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal("10.0000"),
                valid_to=now + timedelta(days=30),
                recorded_at=now - timedelta(days=20 + i),
            )

        # 10x magnitude spike offer at 100.00 GBP
        current = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("100.0000"),
            valid_to=now + timedelta(days=5),
            recorded_at=now,
        )

        service = AlertService(settings)
        alerts = service.list_alerts(member=context.member, kind="decimal_or_quantity_anomaly")
        assert len(alerts.items) == 1
        alert = alerts.items[0]
        assert alert.severity == "critical"
        assert alert.confidence == "high"
        assert alert.action == "review_quotation"
        assert alert.evidence["anomaly_type"] == "magnitude_spike"
        assert alert.evidence["landed_cost_id"] == str(current.landed_cost_id)


def test_delivery_cost_anomaly_live_and_dismissal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    psycopg = pytest.importorskip("psycopg")
    now = datetime.now(UTC)
    with committed_smart_context("delivery-live", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        # Seed supplier commercial term with delivery fee 50.00 and MOV 100.00 (50%)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                cur.execute(
                    """
                    insert into supplier_commercial_term (
                        id, tenant_id, supplier_id, created_by_membership_id,
                        minimum_order_value_amount, minimum_order_value_currency,
                        delivery_fee_amount, delivery_fee_currency
                    ) values (
                        gen_random_uuid(), %s, %s, %s,
                        100.0000, 'GBP', 50.0000, 'GBP'
                    )
                    """,
                    (context.workspace.tenant_id, supplier_id, context.workspace.membership_id),
                )
                conn.commit()

        # Add active offer from supplier
        add_costed_offer(
            context,
            supplier_id=supplier_id,
            amount=Decimal("15.0000"),
            valid_to=now + timedelta(days=10),
            recorded_at=now,
        )

        service = AlertService(settings)
        alerts = service.list_alerts(member=context.member, kind="delivery_cost_anomaly")
        assert len(alerts.items) == 1
        alert = alerts.items[0]
        assert alert.kind == "delivery_cost_anomaly"
        assert alert.severity == "warning"
        assert alert.confidence == "high"
        assert alert.action == "view_delivery_issues"

        # Dismiss
        service.dismiss_alert(member=context.member, alert_id=alert.id)
        after_dismissal = service.list_alerts(member=context.member, kind="delivery_cost_anomaly")
        assert alert.id not in {a.id for a in after_dismissal.items}
