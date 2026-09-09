from procurepilot_api.modules.matching.quoted_exposure import quoted_exposure
from procurepilot_api.modules.quotations.schemas import Money


def money(amount: str, currency: str = "GBP") -> Money:
    return Money(amount=amount, currency=currency)


def test_quoted_exposure_applies_vat_delivery_and_discount() -> None:
    result = quoted_exposure(
        quantity="10",
        unit_price=money("2.5000"),
        vat_rate="0.2000",
        delivery_fee=money("5.0000"),
        discount=money("1.0000"),
    )

    assert result.total == money("34.8000")
    assert result.issue is None


def test_quoted_exposure_preserves_decimal_precision() -> None:
    result = quoted_exposure(
        quantity="3",
        unit_price=money("0.3333"),
        vat_rate=None,
        delivery_fee=None,
        discount=None,
    )

    assert result.total == money("0.9999")


def test_quoted_exposure_requires_quantity_and_unit_price() -> None:
    assert quoted_exposure(quantity=None, unit_price=money("1.0000")).total is None
    assert quoted_exposure(quantity="1", unit_price=None).total is None


def test_quoted_exposure_rejects_mixed_currencies() -> None:
    result = quoted_exposure(
        quantity="10",
        unit_price=money("2.5000"),
        vat_rate="0.2000",
        delivery_fee=money("5.0000", "USD"),
        discount=None,
    )

    assert result.total is None
    assert result.issue == "currency_mismatch"
