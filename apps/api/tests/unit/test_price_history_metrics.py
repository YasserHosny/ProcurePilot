from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from procurepilot_api.modules.offers.price_history import price_history_summary
from procurepilot_api.modules.offers.schemas import Money, PriceHistoryPoint


def point(amount: str, recorded_at: datetime) -> PriceHistoryPoint:
    return PriceHistoryPoint(
        landed_cost_id=uuid4(),
        workspace_product_id=uuid4(),
        supplier_id=uuid4(),
        supplier_name="Supplier",
        recorded_at=recorded_at,
        valid_from=recorded_at,
        normalised_unit_price=Money(amount=amount, currency="GBP"),
        landed_cost_total=Money(amount=amount, currency="GBP"),
        quantity="1.000000",
        base_unit="kg",
    )


def test_price_history_metrics_use_last_rolling_average_and_all_time_best() -> None:
    now = datetime.now(UTC)
    old = point("3.0000", now - timedelta(days=250))
    first = point("2.0000", now - timedelta(days=20))
    latest = point("4.0000", now)
    summary = price_history_summary([old, first, latest], window_start=now - timedelta(days=186))
    assert summary.last_paid is not None
    assert summary.last_paid.value.amount == "4.0000"
    assert summary.average_paid_rolling_window is not None
    assert summary.average_paid_rolling_window.value.amount == "3.0000"
    assert summary.best_price is not None
    assert summary.best_price.value.amount == "2.0000"
