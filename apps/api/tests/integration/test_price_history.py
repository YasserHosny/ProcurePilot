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
from procurepilot_api.modules.offers.service import OfferService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_price_history_metrics_are_derived_from_real_landed_cost_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    now = datetime.now(UTC)
    with committed_smart_context("price-history") as context:
        first = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("30.0000"),
            recorded_at=now - timedelta(days=40),
        )
        best = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[1],
            amount=Decimal("15.0000"),
            recorded_at=now - timedelta(days=20),
        )
        latest = add_costed_offer(
            context,
            supplier_id=context.supplier_ids[0],
            amount=Decimal("45.0000"),
            recorded_at=now,
        )

        history = OfferService(settings).price_history(
            member=context.member,
            product_id=context.product_id,
            window_months=6,
        )

        assert {point.landed_cost_id for point in history.points} == {
            first.landed_cost_id,
            best.landed_cost_id,
            latest.landed_cost_id,
        }
        assert history.summary.last_paid is not None
        assert history.summary.last_paid.source_landed_cost_ids == [latest.landed_cost_id]
        assert history.summary.last_paid.value.amount == "1.5000"
        assert history.summary.average_paid_rolling_window is not None
        assert history.summary.average_paid_rolling_window.value.amount == "1.0000"
        assert set(history.summary.average_paid_rolling_window.source_landed_cost_ids) == {
            first.landed_cost_id,
            best.landed_cost_id,
            latest.landed_cost_id,
        }
        assert history.summary.best_price is not None
        assert history.summary.best_price.source_landed_cost_ids == [best.landed_cost_id]
        assert history.summary.best_price.value.amount == "0.5000"
