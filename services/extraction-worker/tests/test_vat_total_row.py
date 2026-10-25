from __future__ import annotations

import pytest

from procurepilot_extraction_worker.azure_di import (
    _clean_number,
    _find_grand_total,
    _is_before_tax_row,
    _is_total_row,
    _numeric_cell_amount,
    _parse_invoice_result,
)
from procurepilot_extraction_worker.validation import validate_arithmetic
from procurepilot_extraction_worker.worker import SupplierMatch, _review_reason


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


def test_total_labels_without_whitelisted_wording_reconcile() -> None:
    # «إجمالي القيمة»
    payload_ar = _make_table_payload(
        [["بند 1", "1", "1,000.00", "1,000.00"]],
        "إجمالي القيمة",
        "1,000.00 ر.س",
    )
    result_ar = _parse_invoice_result(payload_ar, "layout:test")
    assert len(result_ar.lines) == 1
    assert result_ar.expected_line_count == 1
    assert result_ar.stated_total is not None
    assert result_ar.stated_total.value == {"amount": "1000.00", "currency": "SAR"}
    assert validate_arithmetic(result_ar).status == "reconciled"

    # "Total Value"
    payload_en = _make_table_payload(
        [["Item 1", "2", "500.00", "1,000.00"]],
        "Total Value",
        "1,000.00 SAR",
    )
    result_en = _parse_invoice_result(payload_en, "layout:test")
    assert len(result_en.lines) == 1
    assert result_en.expected_line_count == 1
    assert result_en.stated_total is not None
    assert result_en.stated_total.value == {"amount": "1000.00", "currency": "SAR"}
    assert validate_arithmetic(result_en).status == "reconciled"


def test_item_label_with_glued_letters_stays_a_line() -> None:
    # «مجموعة أدوات» starts with «مجموعة», which is glued to «ة» and must NOT be a total
    payload = _make_table_payload(
        [["مجموعة أدوات", "2", "50.00", "100.00"]],
        "الإجمالي",
        "100.00 ر.س",
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == 1
    assert result.lines[0].original_text == "مجموعة أدوات"
    assert result.expected_line_count == 1
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "100.00", "currency": "SAR"}
    assert validate_arithmetic(result).status == "reconciled"


def test_visual_order_rate_adjacent_to_amount() -> None:
    # F2: "4,440.00 %15" must not swallow 4,440.00 as percentage
    text = "الإجمالي شامل ضريبة 4,440.00 %15 ر.س"
    field = _find_grand_total(text, "SAR")
    assert field is not None
    assert field.value == {"amount": "4440.00", "currency": "SAR"}

    # In a table total row
    payload = _make_table_payload(
        [
            ["بند أول", "2", "1,000.00", "2,000.00"],
            ["بند ثان", "2", "1,220.00", "2,440.00"],
        ],
        "الإجمالي شامل ضريبة 4,440.00 %15 ر.س",
        "4,440.00 ر.س",
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == 2
    assert result.expected_line_count == 2
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "4440.00", "currency": "SAR"}
    assert validate_arithmetic(result).status == "reconciled"


def test_item_row_with_identical_description_and_quantity_stays_a_line() -> None:
    # 1 (blocking): Real item row like description '1' / quantity '1' must not be dropped
    payload = _make_table_payload(
        [["1", "1", "100.00", "100.00"]],
        "الإجمالي",
        "100.00 ر.س",
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == 1
    assert result.expected_line_count == 1
    assert result.lines[0].original_text == "1"
    assert result.lines[0].fields["quantity"].value == "1"
    assert result.lines[0].fields["unit_price"].value == {"amount": "100.00", "currency": "SAR"}
    assert result.lines[0].fields["line_total"].value == {"amount": "100.00", "currency": "SAR"}
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "100.00", "currency": "SAR"}
    assert validate_arithmetic(result).status == "reconciled"


def test_vat_cell_with_currency_marker_does_not_beat_bare_grand_total() -> None:
    # 2 (blocking): Total | '' | '150.00 ر.س' | '1,150.00' → 1150.00
    # When line_total role is not explicitly bound, fallback_amount must use the last numeric
    # column ('1,150.00'), not the VAT cell with a currency marker ('150.00 ر.س').
    cells = [
        {"rowIndex": 0, "columnIndex": 0, "columnSpan": 1, "content": "الصنف"},
        {"rowIndex": 0, "columnIndex": 1, "columnSpan": 1, "content": "الكمية"},
        {"rowIndex": 0, "columnIndex": 2, "columnSpan": 1, "content": "سعر الوحدة"},
        {"rowIndex": 0, "columnIndex": 3, "columnSpan": 1, "content": "الصافي"},
        {"rowIndex": 1, "columnIndex": 0, "columnSpan": 1, "content": "بند 1"},
        {"rowIndex": 1, "columnIndex": 1, "columnSpan": 1, "content": "1"},
        {"rowIndex": 1, "columnIndex": 2, "columnSpan": 1, "content": "1,000.00"},
        {"rowIndex": 1, "columnIndex": 3, "columnSpan": 1, "content": "1,000.00"},
        {"rowIndex": 2, "columnIndex": 0, "columnSpan": 1, "content": "Total"},
        {"rowIndex": 2, "columnIndex": 1, "columnSpan": 1, "content": ""},
        {"rowIndex": 2, "columnIndex": 2, "columnSpan": 1, "content": "150.00 ر.س"},
        {"rowIndex": 2, "columnIndex": 3, "columnSpan": 1, "content": "1,150.00"},
    ]
    payload = {
        "content": "Total 150.00 ر.س 1,150.00",
        "tables": [{"columnCount": 4, "rowCount": 3, "cells": cells}],
    }
    result = _parse_invoice_result(payload, "layout:test")
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "1150.00", "currency": "SAR"}


def test_total_fallback_loop_scans_right_to_left_and_skips_label() -> None:
    # 3 (blocking): 'إجمالي لعام 2024' | '' | 'المبلغ 1,000.00 ر.س' → 1000.00
    cells = [
        {"rowIndex": 0, "columnIndex": 0, "columnSpan": 1, "content": "الصنف"},
        {"rowIndex": 0, "columnIndex": 1, "columnSpan": 1, "content": "الكمية"},
        {"rowIndex": 0, "columnIndex": 2, "columnSpan": 1, "content": "سعر الوحدة"},
        {"rowIndex": 1, "columnIndex": 0, "columnSpan": 1, "content": "بند"},
        {"rowIndex": 1, "columnIndex": 1, "columnSpan": 1, "content": "1"},
        {"rowIndex": 1, "columnIndex": 2, "columnSpan": 1, "content": "1,000.00"},
        {"rowIndex": 2, "columnIndex": 0, "columnSpan": 1, "content": "إجمالي لعام 2024"},
        {"rowIndex": 2, "columnIndex": 1, "columnSpan": 1, "content": ""},
        {"rowIndex": 2, "columnIndex": 2, "columnSpan": 1, "content": "المبلغ 1,000.00 ر.س"},
    ]
    payload = {
        "content": "إجمالي لعام 2024 المبلغ 1,000.00 ر.س",
        "tables": [{"columnCount": 3, "rowCount": 3, "cells": cells}],
    }
    result = _parse_invoice_result(payload, "layout:test")
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "1000.00", "currency": "SAR"}


def test_arabic_attached_prefixes_recognized_as_totals() -> None:
    # 4 (blocking): «والإجمالي», «بالإجمالي», «فالإجمالي», «للإجمالي»/«لإجمالي»
    for label in ("والإجمالي", "بالإجمالي", "فالإجمالي", "للإجمالي", "لإجمالي"):
        assert _is_total_row(label), f"{label} must be recognized as a total row"
        payload = _make_table_payload(
            [["بند", "1", "1,000.00", "1,000.00"]],
            label,
            "1,000.00 ر.س",
        )
        result = _parse_invoice_result(payload, "layout:test")
        assert len(result.lines) == 1
        assert result.expected_line_count == 1
        assert result.stated_total is not None
        assert result.stated_total.value == {"amount": "1000.00", "currency": "SAR"}


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("إجمالي الفاتورة", True),
        ("إجمالي العرض", True),
        ("Total Cost", True),
        ("Total Value", True),
        ("إجمالي القيمة", True),
        ("والإجمالي: 1500 ر.س", True),
        ("الإجمالي شامل ضريبة القيمة المضافة 15%", True),
        ("مجموعة أدوات", False),
        ("Subtotal", False),
        ("المجموع الفرعي", False),
    ],
)
def test_is_total_row_truth_table(label: str, expected: bool) -> None:
    assert _is_total_row(label) is expected


def test_leading_percent_does_not_swallow_visual_order_amount() -> None:
    # 5 (non-blocking): 'الإجمالي شامل ضريبة 15 :%4,440.00 ر.س' → 4440.00
    text = "الإجمالي شامل ضريبة 15 :%4,440.00 ر.س"
    field = _find_grand_total(text, "SAR")
    assert field is not None
    assert field.value == {"amount": "4440.00", "currency": "SAR"}


def test_items_named_total_clean_or_collection_stay_lines() -> None:
    # Item rows with unit price and line total stay lines even when starting with total words
    payload_ar = _make_table_payload(
        [["مجموع قطع غيار", "1", "100.00", "100.00"]],
        "الإجمالي",
        "100.00 ر.س",
    )
    result_ar = _parse_invoice_result(payload_ar, "layout:test")
    assert len(result_ar.lines) == 1
    assert result_ar.lines[0].original_text == "مجموع قطع غيار"
    assert result_ar.stated_total is not None
    assert result_ar.stated_total.value == {"amount": "100.00", "currency": "SAR"}

    payload_en = _make_table_payload(
        [["Total Clean Detergent", "2", "50.00", "100.00"]],
        "Total",
        "100.00 SAR",
    )
    result_en = _parse_invoice_result(payload_en, "layout:test")
    assert len(result_en.lines) == 1
    assert result_en.lines[0].original_text == "Total Clean Detergent"
    assert result_en.stated_total is not None
    assert result_en.stated_total.value == {"amount": "100.00", "currency": "SAR"}


def test_items_without_quantity_not_swallowed_as_total_row() -> None:
    # In origin/main behaviour, items without quantity are not swallowed as total rows
    # because of the `qty is None and not (price and total)` guard, but they increment
    # expected_line_count without producing an ExtractedLine since qty is missing.
    payload_ar = _make_table_payload(
        [["مجموع قطع غيار", "", "100.00", "100.00"]],
        "الإجمالي",
        "100.00 ر.س",
    )
    result_ar = _parse_invoice_result(payload_ar, "layout:test")
    assert len(result_ar.lines) == 0
    assert result_ar.expected_line_count == 1
    assert result_ar.stated_total is not None
    assert result_ar.stated_total.value == {"amount": "100.00", "currency": "SAR"}

    payload_en = _make_table_payload(
        [["Total Clean Detergent", "", "50.00", "50.00"]],
        "Total",
        "50.00 SAR",
    )
    result_en = _parse_invoice_result(payload_en, "layout:test")
    assert len(result_en.lines) == 0
    assert result_en.expected_line_count == 1
    assert result_en.stated_total is not None
    assert result_en.stated_total.value == {"amount": "50.00", "currency": "SAR"}


def _make_irish_demo_payload(
    item_rows: list[list[str]],
    subtotal: str = "€1,111.00",
    vat: str = "€0.00",
    total: str = "€1,111.00",
    subtotal_label: str = "Subtotal",
) -> dict:
    headers = ["#", "Item", "Pack", "Qty", "Price per pack (excl. VAT)", "Amount"]
    cells: list[dict] = []
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
        {"rowIndex": current_row, "columnIndex": 0, "columnSpan": 5, "content": subtotal_label}
    )
    cells.append({"rowIndex": current_row, "columnIndex": 5, "columnSpan": 1, "content": subtotal})
    current_row += 1

    cells.append(
        {
            "rowIndex": current_row,
            "columnIndex": 0,
            "columnSpan": 5,
            "content": "VAT 0% (zero-rated food)",
        }
    )
    cells.append({"rowIndex": current_row, "columnIndex": 5, "columnSpan": 1, "content": vat})
    current_row += 1

    cells.append({"rowIndex": current_row, "columnIndex": 0, "columnSpan": 5, "content": "Total"})
    cells.append({"rowIndex": current_row, "columnIndex": 5, "columnSpan": 1, "content": total})

    return {
        "content": f"{subtotal_label} {subtotal} VAT 0% {vat} Total {total}",
        "tables": [{"columnCount": 6, "rowCount": current_row + 1, "cells": cells}],
    }


def test_irish_demo_layout_subtotal_reconciles_and_avoids_line_count_mismatch() -> None:
    payload = _make_irish_demo_payload(
        [
            ["1", "Sunflower Oil", "20 L drum", "10", "€43.90", "€439.00"],
            ["2", "Basmati Rice", "10 kg bag", "30", "€22.40", "€672.00"],
        ],
        subtotal="€1,111.00",
        vat="€0.00",
        total="€1,111.00",
    )
    result = _parse_invoice_result(payload, "layout:test")

    assert len(result.lines) == 2
    assert result.expected_line_count == 2 == len(result.lines)
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "1111.00", "currency": "EUR"}

    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"

    no_match = SupplierMatch(supplier_id=None, confidence=None, had_candidates=False)
    review_reason = _review_reason(result, validation.status, 0.85, no_match)
    assert review_reason != "line_count_mismatch"
    assert review_reason is None


def test_irish_demo_layout_one_line_variant_tomatoes() -> None:
    payload = _make_irish_demo_payload(
        [
            ["1", "Tomatoes", "6 kg box", "20", "€13.60", "€272.00"],
        ],
        subtotal="€272.00",
        vat="€0.00",
        total="€272.00",
    )
    result = _parse_invoice_result(payload, "layout:test")

    assert len(result.lines) == 1
    assert result.expected_line_count == 1 == len(result.lines)
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "272.00", "currency": "EUR"}

    validation = validate_arithmetic(result)
    assert validation.status == "reconciled"

    no_match = SupplierMatch(supplier_id=None, confidence=None, had_candidates=False)
    review_reason = _review_reason(result, validation.status, 0.85, no_match)
    assert review_reason != "line_count_mismatch"
    assert review_reason is None


@pytest.mark.parametrize(
    "label",
    ["subtotal", "sub-total", "sub total", "Sub-total", "Sub total", "SUBTOTAL"],
)
def test_subtotal_variants_recognized_as_before_tax(label: str) -> None:
    assert _is_before_tax_row(label) is True
    payload = _make_irish_demo_payload(
        [
            ["1", "Tomatoes", "6 kg box", "20", "€13.60", "€272.00"],
        ],
        subtotal="€272.00",
        vat="€0.00",
        total="€272.00",
        subtotal_label=label,
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert result.expected_line_count == 1 == len(result.lines)
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": "272.00", "currency": "EUR"}


def test_negative_total_weight_and_item_total_weight_handled_as_before() -> None:
    # "Total weight 25 kg" starts with Total so it matches _is_total_row,
    # but it is NOT a before-tax row.
    assert _is_total_row("Total weight 25 kg") is True
    assert _is_before_tax_row("Total weight 25 kg") is False

    # "Item total weight" has total inside, not at the start, so it is neither
    # a total row nor a before-tax row.
    assert _is_total_row("Item total weight") is False
    assert _is_before_tax_row("Item total weight") is False

    # An item row named "Total weight 25 kg" with price and total stays a line
    payload_line = _make_table_payload(
        [["Total weight 25 kg", "1", "50.00", "50.00"]],
        "Total",
        "50.00 EUR",
    )
    result_line = _parse_invoice_result(payload_line, "layout:test")
    assert len(result_line.lines) == 1
    assert result_line.lines[0].original_text == "Total weight 25 kg"
    assert result_line.expected_line_count == 1

    # An item row named "Total weight 25 kg" with price/total but missing quantity
    # is not swallowed as a total row; it increments expected without adding a line
    payload_no_qty = _make_table_payload(
        [["Total weight 25 kg", "", "50.00", "50.00"]],
        "Total",
        "50.00 EUR",
    )
    result_no_qty = _parse_invoice_result(payload_no_qty, "layout:test")
    assert len(result_no_qty.lines) == 0
    assert result_no_qty.expected_line_count == 1

    # Summary row with "Total weight 25 kg" with no price and no total in a table
    # behaves as before (recognized as total row, not before-tax, and overridden by Grand Total)
    cells = [
        {"rowIndex": 0, "columnIndex": 0, "columnSpan": 1, "content": "Item"},
        {"rowIndex": 0, "columnIndex": 1, "columnSpan": 1, "content": "Qty"},
        {"rowIndex": 0, "columnIndex": 2, "columnSpan": 1, "content": "Price"},
        {"rowIndex": 0, "columnIndex": 3, "columnSpan": 1, "content": "Amount"},
        {"rowIndex": 1, "columnIndex": 0, "columnSpan": 1, "content": "Oil"},
        {"rowIndex": 1, "columnIndex": 1, "columnSpan": 1, "content": "10"},
        {"rowIndex": 1, "columnIndex": 2, "columnSpan": 1, "content": "€43.90"},
        {"rowIndex": 1, "columnIndex": 3, "columnSpan": 1, "content": "€439.00"},
        {"rowIndex": 2, "columnIndex": 0, "columnSpan": 3, "content": "Total weight 25 kg"},
        {"rowIndex": 2, "columnIndex": 3, "columnSpan": 1, "content": ""},
        {"rowIndex": 3, "columnIndex": 0, "columnSpan": 3, "content": "Total"},
        {"rowIndex": 3, "columnIndex": 3, "columnSpan": 1, "content": "€439.00"},
    ]
    payload_summary = {
        "content": "Oil 10 €43.90 €439.00 Total weight 25 kg Total €439.00",
        "tables": [{"columnCount": 4, "rowCount": 4, "cells": cells}],
    }
    result_summary = _parse_invoice_result(payload_summary, "layout:test")
    assert len(result_summary.lines) == 1
    assert result_summary.expected_line_count == 1
    assert result_summary.stated_total is not None
    assert result_summary.stated_total.value == {"amount": "439.00", "currency": "EUR"}
