from decimal import Decimal

import pytest


@pytest.mark.parametrize(
    "phrase",
    [
        "الأسعار شاملة ضريبة القيمة المضافة 15%",
        "السعر شامل ضريبة القيمة المضافة 15%",
        "شاملة ضريبة القيمة المضافة 15%",
        "شامل ضريبة القيمة المضافة 15%",
        "الأسعار شاملة ضريبة القيمة المضافة ١٥٪",
        "Prices include VAT (15%)",
        "Prices include VAT 15%",
        "prices incl. VAT 15%",
        "inclusive of VAT 15%",
        "VAT inclusive 15%",
        "incl. VAT 15%",
    ],
)
def test_explicit_price_statements(phrase: str) -> None:
    from procurepilot_extraction_worker.vat_basis import detect_vat_basis

    result = detect_vat_basis(phrase, line_sum=None, stated_total=None)
    assert result is not None
    assert result.prices_include_vat is True
    assert result.rate == Decimal("0.15")
    assert result.evidence == phrase
    assert result.confidence == 0.80


@pytest.mark.parametrize("label", ["الإجمالي شامل ضريبة القيمة المضافة 15%", "Total incl. VAT 15%"])
@pytest.mark.parametrize(
    "line_sum,stated,expected",
    [
        ("100", "100", True),
        ("100", "115", False),
        ("100", "100.01", True),
        ("100", "114.99", False),
        ("100", "107", None),
        (None, "115", None),
    ],
)
def test_total_label_requires_arithmetic(
    label: str, line_sum: str | None, stated: str, expected: bool | None
) -> None:
    from procurepilot_extraction_worker.vat_basis import detect_vat_basis

    result = detect_vat_basis(
        label, line_sum=Decimal(line_sum) if line_sum else None, stated_total=Decimal(stated)
    )
    if expected is None:
        assert result is None
    else:
        assert result.prices_include_vat is expected
        assert result.rate == Decimal("0.15")


@pytest.mark.parametrize(
    "text",
    [
        "Prices include VAT",
        "VAT inclusive",
        "inclusive of VAT",
        "الأسعار شاملة ضريبة القيمة المضافة",
        "VAT 15%",
        "No tax statement",
        "Prices include VAT 100%",
        "Prices include VAT -15%",
    ],
)
def test_missing_or_invalid_rate_or_statement_is_not_guessed(text: str) -> None:
    from procurepilot_extraction_worker.vat_basis import detect_vat_basis

    assert detect_vat_basis(text, line_sum=None, stated_total=None) is None
