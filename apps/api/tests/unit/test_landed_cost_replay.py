from decimal import Decimal

from procurepilot_api.modules.landed_cost.rules import (
    RULE_VERSION_V1,
    LandedCostInputs,
    MoneyValue,
    compute_landed_cost,
    replay_landed_cost,
)


def test_landed_cost_replay_from_raw_inputs_is_bit_identical() -> None:
    result = compute_landed_cost(
        LandedCostInputs(
            quantity=Decimal("2"),
            normalised_base_quantity=Decimal("20"),
            base_unit="kilogram",
            unit_price=MoneyValue(Decimal("12.0000"), "GBP"),
            vat_rate=None,
            delivery_fee=MoneyValue(Decimal("1.0000"), "GBP"),
            discount=MoneyValue(Decimal("0.5000"), "GBP"),
        )
    )
    replayed = replay_landed_cost(result.raw_inputs, rule_version=RULE_VERSION_V1)
    assert replayed.raw_inputs == result.raw_inputs
    assert replayed.total.amount == result.total.amount
    assert replayed.vat_rate == Decimal("0.0000")


def test_v2_inclusive_replay_is_identical() -> None:
    result = compute_landed_cost(
        LandedCostInputs(
            quantity=Decimal("350"),
            normalised_base_quantity=Decimal("350"),
            base_unit="each",
            unit_price=MoneyValue(Decimal("13.80"), "SAR"),
            vat_rate=Decimal("0.15"),
            delivery_fee=MoneyValue(Decimal("0"), "SAR"),
            discount=MoneyValue(Decimal("0"), "SAR"),
            prices_include_vat=True,
        ),
        rule_version="landed-cost-v2",
    )
    assert replay_landed_cost(result.raw_inputs, rule_version="landed-cost-v2") == result
