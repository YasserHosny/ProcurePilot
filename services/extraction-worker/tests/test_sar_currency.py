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


@pytest.mark.parametrize(
    "text",
    [
        "100 ر.س",
        "ر. س 100",
        "100 ر.س.",
        "ريال سعودي 100",
        "SAR 100",
        "100 SAR",
        "SR 100",
        "100 SR",
        "SR 250",
        "250 SR",
        "١٬٢٣٤٫٥٠ ر.س",
    ],
)
def test_sar_markers_touching_amount(text: str) -> None:
    assert detect_currency(text) == "SAR"
    fields = {"InvoiceTotal": NS(content=text, confidence=0.9)}
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert result.header["currency"].value == "SAR"
    assert result.stated_total.value["currency"] == "SAR"


@pytest.mark.parametrize("marker", ["ر.س", "ر. س", "ر.س.", "ريال سعودي", "SAR", "SR"])
def test_sar_numeric_cells(marker: str) -> None:
    text = f"١٬٢٣٤٫٥٠ {marker}"
    assert parse_localised_decimal(text) == Decimal("1234.50")
    assert _clean_number(text) == "1234.50"
    assert _numeric_cell_amount(text) == "1234.50"


@pytest.mark.parametrize("text", ["10 EGP, 20 ر.س", "10 جنيه / SR 20", "SAR 10, 20 USD"])
def test_sar_conflicting_markers_are_unknown(text: str) -> None:
    assert detect_currency(text) is None
    assert _has_currency_conflict(text)
    result = _parse_invoice_result(
        NS(documents=[NS(fields={"InvoiceTotal": NS(content=text, confidence=0.9)})]), "test"
    )
    assert "currency" not in result.header


@pytest.mark.parametrize(
    "text", ["MSRP 100", "100 SRI", "SR bolts 100", "ريال للقطعة 100", "SAR", "100"]
)
def test_sar_requires_amount_adjacency_and_token_boundaries(text: str) -> None:
    assert detect_currency(text) is None


def test_unrelated_sr_word_does_not_conflict_with_egp() -> None:
    assert detect_currency("MSRP 100, 20 EGP") == "EGP"


@pytest.mark.parametrize("mixed", [False, True])
def test_sar_layout_preserves_amounts_and_clears_conflicting_currency(mixed: bool) -> None:
    cells = [
        {"rowIndex": row, "columnIndex": col, "content": content}
        for row, values in enumerate(
            [
                ["Description", "Quantity", "Unit price", "Total"],
                ["Rice", "٢", "١٢٫٥٠ ر.س.", "٢٥٫٠٠ ر.س."],
            ]
        )
        for col, content in enumerate(values)
    ]
    payload = {
        "content": "25 EGP" if mixed else "Total ٢٥٫٠٠ ر.س.",
        "tables": [{"columnCount": 4, "rowCount": 2, "cells": cells}],
    }
    result = _parse_invoice_result(payload, "test")
    assert result.expected_line_count == 1
    assert result.lines[0].fields["quantity"].value == "2"
    assert result.lines[0].fields["unit_price"].value == {
        "amount": "12.50",
        "currency": None if mixed else "SAR",
    }
    if mixed:
        assert "currency" not in result.header
    else:
        assert result.header["currency"].value == "SAR"
        assert result.stated_total.value == {"amount": "25.00", "currency": "SAR"}


def test_unattached_currency_word_does_not_conflict_with_sar() -> None:
    text = "EGP catalogue: rice 100 SAR"
    assert detect_currency(text) == "SAR"
    assert not _has_currency_conflict(text)
    result = _parse_invoice_result(
        NS(documents=[NS(fields={"InvoiceTotal": NS(content=text, confidence=0.9)})]), "test"
    )
    assert result.header["currency"].value == "SAR"


@pytest.mark.parametrize(
    "text",
    [
        "100 ريال",
        "ريال 100",
        "100 ريال قطري",
        "100 ريال عماني",
        "100 ريال عُماني",
        "100 QAR",
        "Ref 2026\nSr. Description",
        "Ref 2026\nSR Description",
        "SR\n250",
        "250\nSR",
        "sr 250",
        "250 sr",
    ],
)
def test_ambiguous_riyals_and_serial_headers_are_unresolved(text: str) -> None:
    assert detect_currency(text) is None
    fields = {"InvoiceTotal": NS(content=text, confidence=0.9)}
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert "currency" not in result.header
    if result.stated_total:
        assert result.stated_total.value["currency"] is None


@pytest.mark.parametrize("marker", ["ريال قطري", "ريال عماني", "ريال عُماني", "QAR"])
@pytest.mark.parametrize("home_marker", ["SAR", "EGP"])
def test_other_riyals_conflict_with_evidenced_currency(marker: str, home_marker: str) -> None:
    text = f"100 {home_marker}, 200 {marker}"
    assert detect_currency(text) is None
    assert _has_currency_conflict(text)
    fields = {"InvoiceTotal": NS(content=text, confidence=0.9)}
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert "currency" not in result.header
