from __future__ import annotations

from procurepilot_extraction_worker.azure_di import (
    _clean_number,
    _find_grand_total,
    _numeric_cell_amount,
    _parse_invoice_result,
)
from procurepilot_extraction_worker.validation import validate_arithmetic


def _make_table_payload(item_rows: list[list[str]], total_label: str, total_amount: str) -> dict:
    cells: list[dict] = []
    headers = ["الصنف", "الكمية", "سعر الوحدة", "الإجمالي"]
    for col, h in enumerate(headers):
        cells.append({"rowIndex": 0, "columnIndex": col, "columnSpan": 1, "content": h})

    current_row = 1
    for row_data in item_rows:
        for col, val in enumerate(row_data):
            cells.append(
                {"rowIndex": current_row, "columnIndex": col, "columnSpan": 1, "content": val}
            )
        current_row += 1

    cells.append(
        {"rowIndex": current_row, "columnIndex": 0, "columnSpan": 3, "content": total_label}
    )
    cells.append(
        {"rowIndex": current_row, "columnIndex": 3, "columnSpan": 1, "content": total_amount}
    )

    return {
        "content": f"{total_label} {total_amount}",
        "tables": [{"columnCount": 4, "rowCount": current_row + 1, "cells": cells}],
    }


def test_vat_total_row_two_items_reconciles_sar() -> None:
    payload = _make_table_payload(
        [
            ["بند أول", "2", "1,000.00", "2,000.00"],
            ["بند ثان", "2", "1,220.00", "2,440.00"],
        ],
        "الإجمالي شامل ضريبة القيمة المضافة 15%",
        "4,440.00 ر.س",
    )
    result = _parse_invoice_result(payload, "layout:test")

    assert len(result.lines) == 2
    assert result.expected_line_count == 2
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "4440.00", "currency": "SAR"}
    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"


def test_vat_total_row_three_items_reconciles_sar() -> None:
    payload = _make_table_payload(
        [
            ["بند 1", "1", "1,000.00", "1,000.00"],
            ["بند 2", "2", "1,500.00", "3,000.00"],
            ["بند 3", "1", "1,100.00", "1,100.00"],
        ],
        "الإجمالي شامل ضريبة القيمة المضافة 15%",
        "5,100.00 ر.س",
    )
    result = _parse_invoice_result(payload, "layout:test")

    assert len(result.lines) == 3
    assert result.expected_line_count == 3
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "5100.00", "currency": "SAR"}
    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"


def test_paragraph_text_vat_total_arabic() -> None:
    text_ltr = "الإجمالي شامل ضريبة القيمة المضافة 15%: 4,440.00 ر.س"
    field_ltr = _find_grand_total(text_ltr, "SAR")
    assert field_ltr is not None
    assert field_ltr.value == {"amount": "4440.00", "currency": "SAR"}

    text_visual_rtl = "4,440.00 ر.س :الإجمالي شامل ضريبة القيمة المضافة 15%"
    field_rtl = _find_grand_total(text_visual_rtl, "SAR")
    assert field_rtl is not None
    assert field_rtl.value == {"amount": "4440.00", "currency": "SAR"}


def test_paragraph_text_vat_total_english() -> None:
    text = "Total incl. VAT 15%  SAR 4,440.00"
    field = _find_grand_total(text, "SAR")
    assert field is not None
    assert field.value == {"amount": "4440.00", "currency": "SAR"}

    text_reversed = "SAR 4,440.00 Total incl. VAT 15%"
    field_reversed = _find_grand_total(text_reversed, "SAR")
    assert field_reversed is not None
    assert field_reversed.value == {"amount": "4440.00", "currency": "SAR"}


def test_percentage_never_taken_as_money_or_line_quantity_or_price() -> None:
    assert _clean_number("15%") is None
    assert _clean_number("15 %") is None
    assert _clean_number("15 ٪") is None
    assert _clean_number("١٥٪") is None
    assert _clean_number("15.00%") is None
    assert _numeric_cell_amount("15%") is None
    assert _numeric_cell_amount("15 ٪") is None
    assert _numeric_cell_amount("١٥٪") is None

    # Egyptian «الإجمالي» keeps working
    payload = _make_table_payload(
        [["بند مصري", "1", "200.00", "200.00"]],
        "الإجمالي",
        "200.00 ج.م",
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == 1
    assert result.expected_line_count == 1
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "200.00", "currency": "EGP"}
    assert validate_arithmetic(result).status == "reconciled"
