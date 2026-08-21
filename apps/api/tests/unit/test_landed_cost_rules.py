from decimal import Decimal

from procurepilot_api.modules.landed_cost.rules import (
    RULE_VERSION_V1,
    LandedCostInputs,
    MoneyValue,
    compute_landed_cost,
)


def test_landed_cost_v1_formula_derives_vat_and_zero_other_charges() -> None:
    result = compute_landed_cost(
        LandedCostInputs(
            quantity=Decimal("10"),
            normalised_base_quantity=Decimal("60"),
            base_unit="each",
            unit_price=MoneyValue(Decimal("12.5000"), "GBP"),
            vat_rate=Decimal("0.2000"),
            delivery_fee=MoneyValue(Decimal("5.0000"), "GBP"),
            discount=MoneyValue(Decimal("10.0000"), "GBP"),
        )
    )
    assert result.rule_version == RULE_VERSION_V1
    assert result.vat_amount.amount == Decimal("25.0000")
    assert result.other_charges.amount == Decimal("0.0000")
    assert result.total.amount == Decimal("145.0000")
    assert result.total.currency == "GBP"
