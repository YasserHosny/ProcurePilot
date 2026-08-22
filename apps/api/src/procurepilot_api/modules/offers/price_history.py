from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from procurepilot_api.modules.offers.schemas import (
    Money,
    PriceHistoryMetric,
    PriceHistoryPoint,
    PriceHistorySummary,
)

MONEY_QUANT = Decimal("0.0001")


def normalised_unit_price(total_amount: object, base_quantity: object) -> Decimal:
    return (Decimal(str(total_amount)) / Decimal(str(base_quantity))).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )


def price_history_summary(
    points: list[PriceHistoryPoint],
    *,
    window_start: datetime,
) -> PriceHistorySummary:
    if not points:
        return PriceHistorySummary(
            last_paid=None,
            average_paid_rolling_window=None,
            best_price=None,
        )
    last_point = max(points, key=lambda point: (point.recorded_at, str(point.landed_cost_id)))
    best_point = min(points, key=lambda point: Decimal(point.normalised_unit_price.amount))
    window_points = [point for point in points if point.recorded_at >= window_start]
    average = None
    if window_points:
        total = sum(Decimal(point.normalised_unit_price.amount) for point in window_points)
        value = (total / Decimal(len(window_points))).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        average = PriceHistoryMetric(
            value=Money(
                amount=format(value, "f"),
                currency=window_points[0].normalised_unit_price.currency,
            ),
            source_landed_cost_ids=[point.landed_cost_id for point in window_points],
        )
    return PriceHistorySummary(
        last_paid=PriceHistoryMetric(
            value=last_point.normalised_unit_price,
            source_landed_cost_ids=[last_point.landed_cost_id],
        ),
        average_paid_rolling_window=average,
        best_price=PriceHistoryMetric(
            value=best_point.normalised_unit_price,
            source_landed_cost_ids=[best_point.landed_cost_id],
        ),
    )
