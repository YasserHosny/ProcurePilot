"""Deterministic R4.0 demand forecast calculation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Literal

ForecastState = Literal["ready", "provisional", "insufficient_data"]
ForecastConfidence = Literal["high", "medium", "low"]

MODEL_VERSION = "forecast-v1"
G3_HISTORY_DAYS = 180
DECIMAL_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class ForecastInput:
    sales_velocity_per_day: Decimal | None
    stock_on_hand: Decimal | None
    observed_history_days: int | None
    horizon_days: int = 14
    safety_days: int = 3
    rounding_increment: Decimal = Decimal("1")


@dataclass(frozen=True)
class ForecastResult:
    state: ForecastState
    confidence: ForecastConfidence
    expected_daily_demand: Decimal | None
    expected_demand: Decimal | None
    uncertainty_lower: Decimal | None
    uncertainty_upper: Decimal | None
    stock_on_hand: Decimal | None
    suggested_quantity: Decimal | None
    observed_history_days: int | None
    model_version: str = MODEL_VERSION
    release_posture: str = "g3_unmet"


def calculate_forecast(values: ForecastInput) -> ForecastResult:
    """Calculate one forecast without I/O or clock access.

    The function intentionally refuses to invent a demand or stock value. This keeps cold-start
    behavior explicit and makes the calculation replayable from a stored signal snapshot.
    """

    if (
        values.sales_velocity_per_day is None
        or values.stock_on_hand is None
        or values.observed_history_days is None
        or values.observed_history_days <= 0
        or values.horizon_days <= 0
        or values.safety_days < 0
        or values.rounding_increment <= 0
    ):
        return ForecastResult(
            state="insufficient_data",
            confidence="low",
            expected_daily_demand=None,
            expected_demand=None,
            uncertainty_lower=None,
            uncertainty_upper=None,
            stock_on_hand=values.stock_on_hand,
            suggested_quantity=None,
            observed_history_days=values.observed_history_days,
        )

    daily = _quantize(max(values.sales_velocity_per_day, Decimal("0")))
    expected = _quantize(daily * values.horizon_days)
    uncertainty_factor = _uncertainty_factor(values.observed_history_days)
    uncertainty = _quantize(max(expected * uncertainty_factor, DECIMAL_PLACES))
    lower = _quantize(max(Decimal("0"), expected - uncertainty))
    upper = _quantize(expected + uncertainty)
    safety_stock = _quantize(daily * values.safety_days)
    suggested = _ceil_to_increment(
        max(Decimal("0"), expected + safety_stock - values.stock_on_hand),
        values.rounding_increment,
    )
    state: ForecastState = (
        "ready" if values.observed_history_days >= G3_HISTORY_DAYS else "provisional"
    )

    return ForecastResult(
        state=state,
        confidence=_confidence(values.observed_history_days),
        expected_daily_demand=daily,
        expected_demand=expected,
        uncertainty_lower=lower,
        uncertainty_upper=upper,
        stock_on_hand=_quantize(max(values.stock_on_hand, Decimal("0"))),
        suggested_quantity=_quantize(suggested),
        observed_history_days=values.observed_history_days,
    )


def _uncertainty_factor(observed_history_days: int) -> Decimal:
    if observed_history_days >= G3_HISTORY_DAYS:
        return Decimal("0.10")
    if observed_history_days >= 90:
        return Decimal("0.20")
    return Decimal("0.35")


def _confidence(observed_history_days: int) -> ForecastConfidence:
    if observed_history_days >= G3_HISTORY_DAYS:
        return "high"
    if observed_history_days >= 90:
        return "medium"
    return "low"


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_PLACES)


def _ceil_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    units = (value / increment).to_integral_value(rounding=ROUND_CEILING)
    return units * increment
