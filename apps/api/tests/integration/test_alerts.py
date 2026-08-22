from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
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


def test_alerts_are_live_dismissible_and_recur_when_condition_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("alerts-live", supplier_count=1) as context:
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("1.0000"),
            valid_to=now + timedelta(days=30),
            recorded_at=now - timedelta(days=30),
        )
        add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("1.0000"),
            valid_to=now + timedelta(days=30),
            recorded_at=now - timedelta(days=20),
        )
        first_current = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("10.0000"),
            valid_to=now + timedelta(days=2),
            recorded_at=now,
        )

        service = AlertService(settings)
        first_list = service.list_alerts(member=context.member)
        kinds = {alert.kind for alert in first_list.items}
        assert "recommended_price_expiring" in kinds
        assert "price_swing" in kinds
        expiring = next(
            alert
            for alert in first_list.items
            if alert.kind == "recommended_price_expiring"
        )
        assert expiring.evidence["landed_cost_id"] == str(first_current.landed_cost_id)

        service.dismiss_alert(member=context.member, alert_id=expiring.id)
        after_dismissal = service.list_alerts(member=context.member)
        assert expiring.id not in {alert.id for alert in after_dismissal.items}

        second_current = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("11.0000"),
            valid_to=now + timedelta(days=3),
            recorded_at=now + timedelta(minutes=1),
        )
        after_change = service.list_alerts(member=context.member)
        recurring = [
            alert
            for alert in after_change.items
            if alert.kind == "recommended_price_expiring"
        ]
        assert len(recurring) == 1
        assert recurring[0].id != expiring.id
        assert recurring[0].evidence["landed_cost_id"] == str(second_current.landed_cost_id)
