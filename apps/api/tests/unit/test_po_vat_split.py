from decimal import Decimal

from procurepilot_api.modules.orders.vat_split import net_unit_price, split_vat_inclusive_line


def test_exact_net_and_tax_split() -> None:
    result = split_vat_inclusive_line(Decimal("13.80"), Decimal("100"), Decimal("0.15"))
    assert net_unit_price(Decimal("13.80"), Decimal("0.15")) == Decimal("12.0000")
    assert (result.net_unit_price, result.net_total, result.tax, result.line_total) == (
        Decimal("12.0000"),
        Decimal("1200.0000"),
        Decimal("180.0000"),
        Decimal("1380.0000"),
    )


def test_rounding_residual_goes_to_tax() -> None:
    result = split_vat_inclusive_line(Decimal("10.00"), Decimal("3"), Decimal("0.15"))
    assert (result.net_unit_price, result.net_total, result.tax, result.line_total) == (
        Decimal("8.6957"),
        Decimal("26.0871"),
        Decimal("3.9129"),
        Decimal("30.0000"),
    )


def test_four_lines_reconcile_exactly_to_printed_total() -> None:
    lines = [
        split_vat_inclusive_line(Decimal(price), Decimal(qty), Decimal("0.15"))
        for price, qty in [("86", "20"), ("150", "10"), ("38", "10"), ("82", "15")]
    ]
    assert sum(line.line_total for line in lines) == Decimal("4830.0000")
    assert sum(line.net_total for line in lines) + sum(line.tax for line in lines) == Decimal(
        "4830.0000"
    )
    assert all(line.line_total == line.gross_total for line in lines)
