from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from procurepilot_extraction_worker.azure_di import (
    _clean_number,
    _has_currency_conflict,
    _numeric_cell_amount,
    _parse_invoice_result,
)
from procurepilot_extraction_worker.currency import detect_currency, parse_localised_decimal
from procurepilot_extraction_worker.validation import validate_arithmetic


@pytest.mark.parametrize(
    "text",
    [
        "€100",
        "100 €",
        "€ 100",
        "EUR 100",
        "100 EUR",
        "12.60 euro",
        "€1,234.56",
        "1,234.56 €",
        "EUR 4,410.00",
        "4,410.00 EUR",
        "Total 1,289.50 euros",
        "Total €1,289.50",
    ],
)
def test_eur_markers_touching_amount(text: str) -> None:
    assert detect_currency(text) == "EUR"
    fields = {"InvoiceTotal": NS(content=text, confidence=0.9)}
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert result.header["currency"].value == "EUR"
    assert result.stated_total.value["currency"] == "EUR"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("€1,234.56", Decimal("1234.56")),
        ("1,234.56 €", Decimal("1234.56")),
        ("EUR 4,410.00", Decimal("4410.00")),
        ("4,410.00 EUR", Decimal("4410.00")),
        ("4,410.00 euro", Decimal("4410.00")),
        ("4,410.00 euros", Decimal("4410.00")),
    ],
)
def test_eur_numeric_cells(text: str, expected: Decimal) -> None:
    assert parse_localised_decimal(text) == expected
    formatted = format(expected, "f")
    assert _clean_number(text) == formatted
    assert _numeric_cell_amount(text) == formatted


@pytest.mark.parametrize(
    "text",
    [
        "euro",
        "euros",
        "Euro",
        "EUROS",
        "A bare euro quote with no amount",
        "EUR",
        "€",
        "100",
        "europe 100",
        "100 europe",
        "neuro 100",
        "euro 100",
        "euros 100",
        "Euro 1,289.50",
        "100 euro",
        "100 euros",
        "100 Euro",
        "100 EUROS",
        "10 Euro pallets",
        "10 Euro crates",
        "Euro 5 engine oil",
    ],
)
def test_eur_requires_amount_adjacency_and_token_boundaries(text: str) -> None:
    assert detect_currency(text) is None


def test_euro_word_before_amount_is_not_evidence() -> None:
    assert detect_currency("10 Euro pallets") is None
    assert detect_currency("10 Euro crates") is None
    assert detect_currency("Euro 5 engine oil") is None
    assert detect_currency("Euro 1,289.50") is None
    assert detect_currency("100 euros") is None
    assert detect_currency("100 euro") is None
    assert detect_currency("12.60 euro") == "EUR"
    assert detect_currency("Total 1,289.50 euros") == "EUR"
    assert detect_currency("Total €1,289.50") == "EUR"


@pytest.mark.parametrize(
    "text",
    [
        "100 EUR, 200 SAR",
        "€100 / SR 200",
        "EUR 100, 200 £",
        "€100, £200",
        "100 EUR, 200 USD",
        "12.60 euro, 200 EGP",
        "100 EUR, 200 EGP",
    ],
)
def test_eur_conflicting_markers_are_unknown(text: str) -> None:
    assert detect_currency(text) is None
    assert _has_currency_conflict(text)
    result = _parse_invoice_result(
        NS(documents=[NS(fields={"InvoiceTotal": NS(content=text, confidence=0.9)})]), "test"
    )
    assert "currency" not in result.header


def test_existing_egp_and_sar_behaviour_unchanged() -> None:
    assert detect_currency("100 EGP") == "EGP"
    assert detect_currency("100 SAR") == "SAR"
    assert detect_currency("١٬٢٣٤٫٥٠ ر.س") == "SAR"
    assert detect_currency("100 ج.م") == "EGP"
    assert parse_localised_decimal("١٬٢٣٤٫٥٠ ر.س") == Decimal("1234.50")
    assert parse_localised_decimal("100 EGP") == Decimal("100")


def test_unattached_currency_word_does_not_conflict_with_eur() -> None:
    text = "SAR catalogue: rice 100 EUR"
    assert detect_currency(text) == "EUR"
    assert not _has_currency_conflict(text)
    result = _parse_invoice_result(
        NS(documents=[NS(fields={"InvoiceTotal": NS(content=text, confidence=0.9)})]), "test"
    )
    assert result.header["currency"].value == "EUR"


def test_unattached_euro_word_does_not_conflict_with_other_currencies() -> None:
    assert detect_currency("euro catalogue: rice 100 SAR") == "SAR"
    assert not _has_currency_conflict("euro catalogue: rice 100 SAR")
    assert detect_currency("euro catalogue: rice 100 EGP") == "EGP"
    assert not _has_currency_conflict("euro catalogue: rice 100 EGP")


@pytest.mark.parametrize("mixed", [False, True])
def test_eur_layout_preserves_amounts_and_clears_conflicting_currency(mixed: bool) -> None:
    cells = [
        {"rowIndex": row, "columnIndex": col, "content": content}
        for row, values in enumerate(
            [
                ["Description", "Quantity", "Unit price", "Total"],
                ["Widget", "2", "€12.50", "€25.00"],
            ]
        )
        for col, content in enumerate(values)
    ]
    payload = {
        "content": "25 USD" if mixed else "Total €25.00",
        "tables": [{"columnCount": 4, "rowCount": 2, "cells": cells}],
    }
    result = _parse_invoice_result(payload, "test")
    assert result.expected_line_count == 1
    assert result.lines[0].fields["quantity"].value == "2"
    assert result.lines[0].fields["unit_price"].value == {
        "amount": "12.50",
        "currency": None if mixed else "EUR",
    }
    if mixed:
        assert "currency" not in result.header
    else:
        assert result.header["currency"].value == "EUR"
        assert result.stated_total.value == {"amount": "25.00", "currency": "EUR"}


def test_irish_quote_table_reconciles() -> None:
    cells = [
        {"rowIndex": 0, "columnIndex": 0, "columnSpan": 1, "content": "Description"},
        {"rowIndex": 0, "columnIndex": 1, "columnSpan": 1, "content": "Quantity"},
        {"rowIndex": 0, "columnIndex": 2, "columnSpan": 1, "content": "Unit price"},
        {"rowIndex": 0, "columnIndex": 3, "columnSpan": 1, "content": "Total"},
        {"rowIndex": 1, "columnIndex": 0, "columnSpan": 1, "content": "Consultancy Services"},
        {"rowIndex": 1, "columnIndex": 1, "columnSpan": 1, "content": "1"},
        {"rowIndex": 1, "columnIndex": 2, "columnSpan": 1, "content": "4,410.00"},
        {"rowIndex": 1, "columnIndex": 3, "columnSpan": 1, "content": "4,410.00"},
        {"rowIndex": 2, "columnIndex": 0, "columnSpan": 3, "content": "Subtotal"},
        {"rowIndex": 2, "columnIndex": 3, "columnSpan": 1, "content": "€4,410.00"},
        {"rowIndex": 3, "columnIndex": 0, "columnSpan": 3, "content": "VAT 0%"},
        {"rowIndex": 3, "columnIndex": 3, "columnSpan": 1, "content": "€0.00"},
        {"rowIndex": 4, "columnIndex": 0, "columnSpan": 3, "content": "Total"},
        {"rowIndex": 4, "columnIndex": 3, "columnSpan": 1, "content": "€4,410.00"},
    ]
    payload = {
        "content": "Subtotal €4,410.00\nVAT 0% €0.00\nTotal €4,410.00",
        "tables": [{"columnCount": 4, "rowCount": 5, "cells": cells}],
    }
    result = _parse_invoice_result(payload, "layout:test")

    assert result.header["currency"].value == "EUR"
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "4410.00", "currency": "EUR"}
    assert len(result.lines) == 1
    assert result.lines[0].fields["unit_price"].value == {"amount": "4410.00", "currency": "EUR"}
    assert result.lines[0].fields["line_total"].value == {"amount": "4410.00", "currency": "EUR"}

    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"

    # The VAT-percentage row must not become a line or the total
    assert not any("VAT" in line.original_text for line in result.lines)
    assert not any("0%" in line.original_text for line in result.lines)
    assert result.stated_total.value["amount"] != "0.00"


def test_irish_demo_quote_reconciles() -> None:
    headers = ["#", "Item", "Pack", "Qty", "Price per pack (excl. VAT)", "Amount"]
    cells = [
        {"rowIndex": 0, "columnIndex": col, "columnSpan": 1, "content": h}
        for col, h in enumerate(headers)
    ]

    item_data = [
        ["1", "Sunflower Oil", "20 L drum", "10", "€40.90", "€409.00"],
        ["2", "Basmati Rice", "10 kg bag", "30", "€20.95", "€628.50"],
        ["3", "Tomatoes", "6 kg box", "20", "€12.60", "€252.00"],
    ]
    for row_idx, row in enumerate(item_data, start=1):
        for col_idx, val in enumerate(row):
            cells.append(
                {"rowIndex": row_idx, "columnIndex": col_idx, "columnSpan": 1, "content": val}
            )

    totals = [
        ("Subtotal", "€1,289.50"),
        ("VAT 0% (zero-rated food)", "€0.00"),
        ("Total", "€1,289.50"),
    ]
    for row_idx, (label, amt) in enumerate(totals, start=4):
        cells.append({"rowIndex": row_idx, "columnIndex": 0, "columnSpan": 5, "content": label})
        cells.append({"rowIndex": row_idx, "columnIndex": 5, "columnSpan": 1, "content": amt})

    payload = {
        "content": (
            "Currency: Euro (EUR)\n"
            "Prices exclude VAT; all items are zero-rated.\n"
            "Subtotal €1,289.50\n"
            "VAT 0% (zero-rated food) €0.00\n"
            "Total €1,289.50"
        ),
        "tables": [{"columnCount": 6, "rowCount": 7, "cells": cells}],
    }

    result = _parse_invoice_result(payload, "layout:test")

    assert result.header["currency"].value == "EUR"
    assert len(result.lines) == 3

    assert result.lines[0].original_text == "Sunflower Oil"
    assert result.lines[0].fields["quantity"].value == "10"
    assert result.lines[0].fields["unit_price"].value == {"amount": "40.90", "currency": "EUR"}
    assert result.lines[0].fields["line_total"].value == {"amount": "409.00", "currency": "EUR"}

    assert result.lines[1].original_text == "Basmati Rice"
    assert result.lines[1].fields["quantity"].value == "30"
    assert result.lines[1].fields["unit_price"].value == {"amount": "20.95", "currency": "EUR"}
    assert result.lines[1].fields["line_total"].value == {"amount": "628.50", "currency": "EUR"}

    assert result.lines[2].original_text == "Tomatoes"
    assert result.lines[2].fields["quantity"].value == "20"
    assert result.lines[2].fields["unit_price"].value == {"amount": "12.60", "currency": "EUR"}
    assert result.lines[2].fields["line_total"].value == {"amount": "252.00", "currency": "EUR"}

    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "1289.50", "currency": "EUR"}

    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"

    # No VAT or Subtotal row became a line
    assert not any("VAT" in line.original_text for line in result.lines)
    assert not any("Subtotal" in line.original_text for line in result.lines)
