from decimal import Decimal

from procurepilot_extraction_worker.currency import detect_currency, parse_localised_decimal


def test_detects_egyptian_markers_adjacent_to_amounts() -> None:
    for text in (
        "1,250 ج.م",
        "١٢٥٠ جنيه",
        "جنيه مصري 12.50",
        "100 LE",
        "100LE",
        "100 L.E.",
        "EGP 25",
    ):
        assert detect_currency(text) == "EGP"


def test_le_inside_words_and_product_names_is_not_a_currency_marker() -> None:
    assert detect_currency("TABLE 10") is None
    assert detect_currency("Le Pain 10") is None
    assert detect_currency("LE Pain 10") is None


def test_mixed_currency_markers_are_unknown() -> None:
    assert detect_currency("10 EGP, 20 USD") is None
    assert detect_currency("10 ج.م / 20 GBP") is None


def test_arabic_indic_digits_and_separators_are_exact_decimal() -> None:
    assert parse_localised_decimal("١٬٢٣٤٫٥٠") == Decimal("1234.50")
    assert parse_localised_decimal("١٢٣٤٫٥٠") == Decimal("1234.50")
    assert parse_localised_decimal("-١٢٫٧٥") == Decimal("-12.75")
    assert parse_localised_decimal("−١٬٠٠٠٫٠٠") == Decimal("-1000.00")


def test_ascii_comma_only_decimal_remains_ambiguous() -> None:
    try:
        parse_localised_decimal("1,234")
    except ValueError as exc:
        assert "ambiguous decimal separator" in str(exc)
    else:
        raise AssertionError("ASCII comma-only amount must be refused")


def test_negative_amount_with_marker_is_detected() -> None:
    assert detect_currency("-١٢٫٥٠ ج.م") == "EGP"
