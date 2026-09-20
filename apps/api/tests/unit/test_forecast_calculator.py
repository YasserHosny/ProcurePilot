from decimal import Decimal

from procurepilot_api.modules.forecasting.calculator import (
    ForecastInput,
    calculate_forecast,
)


def test_full_history_forecast_is_ready_and_rounded_to_base_unit() -> None:
    result = calculate_forecast(
        ForecastInput(
            sales_velocity_per_day=Decimal("2.5"),
            stock_on_hand=Decimal("4"),
            observed_history_days=180,
            horizon_days=14,
            safety_days=3,
        )
    )

    assert result.state == "ready"
    assert result.confidence == "high"
    assert result.expected_daily_demand == Decimal("2.5000")
    assert result.expected_demand == Decimal("35.0000")
    assert result.uncertainty_lower == Decimal("31.5000")
    assert result.uncertainty_upper == Decimal("38.5000")
    assert result.suggested_quantity == Decimal("39.0000")
    assert result.release_posture == "g3_unmet"


def test_short_history_is_provisional_and_has_wider_uncertainty() -> None:
    result = calculate_forecast(
        ForecastInput(
            sales_velocity_per_day=Decimal("2"),
            stock_on_hand=Decimal("0"),
            observed_history_days=30,
            horizon_days=14,
            safety_days=3,
        )
    )

    assert result.state == "provisional"
    assert result.confidence == "low"
    assert result.uncertainty_lower == Decimal("18.2000")
    assert result.uncertainty_upper == Decimal("37.8000")


def test_rounding_increment_is_respected() -> None:
    result = calculate_forecast(
        ForecastInput(
            sales_velocity_per_day=Decimal("1.1"),
            stock_on_hand=Decimal("0"),
            observed_history_days=90,
            rounding_increment=Decimal("5"),
        )
    )

    assert result.suggested_quantity == Decimal("20.0000")


def test_missing_evidence_is_insufficient_and_has_no_suggested_quantity() -> None:
    result = calculate_forecast(
        ForecastInput(
            sales_velocity_per_day=None,
            stock_on_hand=Decimal("5"),
            observed_history_days=None,
        )
    )

    assert result.state == "insufficient_data"
    assert result.confidence == "low"
    assert result.expected_demand is None
    assert result.suggested_quantity is None


def test_calculation_is_replayable() -> None:
    values = ForecastInput(
        sales_velocity_per_day=Decimal("3.1250"),
        stock_on_hand=Decimal("8"),
        observed_history_days=120,
    )

    assert calculate_forecast(values) == calculate_forecast(values)
