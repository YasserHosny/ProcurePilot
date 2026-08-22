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
            base_unit="kg",
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
