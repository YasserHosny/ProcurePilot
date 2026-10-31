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


def test_v2_inclusive_prices_preserve_printed_total() -> None:
    for price, quantity in [("4830.00", "1"), ("13.80", "350")]:
        result = compute_landed_cost(
            LandedCostInputs(
                quantity=Decimal(quantity),
                normalised_base_quantity=Decimal(quantity),
                base_unit="each",
                unit_price=MoneyValue(Decimal(price), "SAR"),
                vat_rate=Decimal("0.15"),
                delivery_fee=MoneyValue(Decimal("0"), "SAR"),
                discount=MoneyValue(Decimal("0"), "SAR"),
                prices_include_vat=True,
            ),
            rule_version="landed-cost-v2",
        )
        assert result.vat_amount.amount == Decimal("630.0000")
        assert result.total.amount == Decimal("4830.0000")
        assert result.unit_price.amount == Decimal(price)
        assert result.raw_inputs["prices_include_vat"] is True
        assert result.rule_version == "landed-cost-v2"


def test_v2_exclusive_matches_v1_numbers_and_preserves_v1_snapshot() -> None:
    inputs = LandedCostInputs(
        quantity=Decimal("3"),
        normalised_base_quantity=Decimal("3"),
        base_unit="each",
        unit_price=MoneyValue(Decimal("10"), "SAR"),
        vat_rate=Decimal("0.15"),
        delivery_fee=MoneyValue(Decimal("2"), "SAR"),
        discount=MoneyValue(Decimal("1"), "SAR"),
    )
    v1 = compute_landed_cost(inputs)
    v2 = compute_landed_cost(inputs, rule_version="landed-cost-v2")
    assert v1.total == v2.total == MoneyValue(Decimal("35.5000"), "SAR")
    assert v1.vat_amount == v2.vat_amount == MoneyValue(Decimal("4.5000"), "SAR")
    assert "prices_include_vat" not in v1.raw_inputs
    assert v2.raw_inputs == {**v1.raw_inputs, "prices_include_vat": False}
