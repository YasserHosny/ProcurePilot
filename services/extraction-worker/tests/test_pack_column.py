from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from procurepilot_extraction_worker import azure_di
from procurepilot_extraction_worker.models import ExtractedField
from procurepilot_extraction_worker.validation import validate_arithmetic
from procurepilot_extraction_worker.worker import (
    SupplierMatch,
    _normalise_pack_unit,
    _review_reason,
)

FIXTURES = Path(__file__).parent / "fixtures" / "azure_layout"
PACK_FIELDS = {"pack_count", "unit_size", "pack_unit"}


@pytest.mark.parametrize(
    ("text", "count", "size", "unit"),
    [
        ("كيس 10 كجم", 1, "10", "kilogram"),
        ("تنكة 18 لتر", 1, "18", "litre"),
        ("كرتون 12 × 1 لتر", 12, "1", "litre"),
        ("كرتون 12x1 لتر", 12, "1", "litre"),
        ("Carton 24x500g", 24, "0.5", "kilogram"),
        ("كيس ٥٠ كجم", 1, "50", "kilogram"),
        ("علبة 400 جم", 1, "0.4", "kilogram"),
        ("زجاجة 1.5 لتر", 1, "1.5", "litre"),
        ("Bag 25 kg", 1, "25", "kilogram"),
        ("1 L", 1, "1", "litre"),
        ("وعاء 2 لتر", 1, "2", "litre"),
        ("كرتون ١٢ × ١٫٥ لتر", 12, "1.5", "litre"),
        ("Carton ۲۴X۵۰۰g", 24, "0.5", "kilogram"),
        (" Bottle 750 ml ", 1, "0.75", "litre"),
        ("Bottle 250 ml", 1, "0.25", "litre"),
        ("20 L drum", 1, "20", "litre"),
        ("10 kg bag", 1, "10", "kilogram"),
        ("6 kg box", 1, "6", "kilogram"),
    ],
)
def test_parse_pack_text(text: str, count: int, size: str, unit: str) -> None:
    parsed = azure_di.parse_pack_text(text)
    assert parsed is not None
    assert parsed.pack_count == count
    assert parsed.unit_size == Decimal(size)
    assert parsed.pack_unit == unit
    assert _normalise_pack_unit(parsed.pack_unit) == unit


@pytest.mark.parametrize(
    "text",
    [
        "",
        "عبوة غير واضحة",
        "كيس",
        "12 bags",
        "10",
        "Carton 24x500",
        "500 gallons",
        "500gramsExtra",
        "Bag 0 kg",
        "Bag -5 kg",
        "Carton 0x1 L",
        "Carton 1.5x1 L",
        "Carton 12x kg",
        "Carton 12x1x500g",
        "1 L / 2 L",
    ],
)
def test_unrecognisable_pack_text(text: str) -> None:
    assert azure_di.parse_pack_text(text) is None


@pytest.mark.parametrize(
    "header", ["العبوة", "التعبئة", "الحجم", "pack", "packing", "pack size", "packaging"]
)
def test_pack_header_role(header: str) -> None:
    assert azure_di._header_role(header) == "pack"


@pytest.mark.parametrize(
    "header",
    ["سعر العبوة", "سعر العبوة (ر.س)", "سعر التعبئة", "pack price", "pack size price"],
)
def test_pack_price_header_stays_unit_price(header: str) -> None:
    assert azure_di._header_role(header) == "unit_price"


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("packaging amount", "line_total"),
        ("packing qty", "quantity"),
        ("packaging unit", "unit"),
        ("packing rate", "unit_price"),
    ],
)
def test_pack_words_do_not_steal_existing_roles(header: str, role: str) -> None:
    assert azure_di._header_role(header) == role


@pytest.mark.parametrize(
    ("fixture", "prices", "total"),
    [
        ("round1-dh-26-1252", ["85.00", "151.00", "39.00", "81.00"], "4147.00"),
        ("round1-wf-2026-0781", ["86.00", "149.00", "38.00", "80.00"], "4140.00"),
    ],
)
@pytest.mark.parametrize("reverse_columns", [False, True])
def test_round1_fixture_keeps_pack_and_arithmetic(
    fixture: str, prices: list[str], total: str, reverse_columns: bool
) -> None:
    payload = json.loads((FIXTURES / f"{fixture}.layout.json").read_text())
    if reverse_columns:
        for cell in payload["tables"][0]["cells"]:
            cell["columnIndex"] = 6 - cell["columnIndex"] - cell.get("columnSpan", 1)
    result = azure_di._parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == result.expected_line_count == 4
    assert [line.original_text for line in result.lines] == [
        "أرز بسمتي",
        "زيت دوار الشمس",
        "سكر أبيض",
        "دقيق",
    ]
    assert [line.fields["quantity"].value for line in result.lines] == ["25", "6", "12", "8"]
    assert [line.fields["unit_price"].value for line in result.lines] == [
        {"amount": price, "currency": "SAR"} for price in prices
    ]
    for line, size, unit in zip(
        result.lines,
        ["10", "18", "10", "45"],
        ["kilogram", "litre", "kilogram", "kilogram"],
        strict=True,
    ):
        assert line.fields["pack_count"].value == 1
        assert Decimal(line.fields["unit_size"].value) == Decimal(size)
        assert line.fields["pack_unit"].value == unit
        assert "pack_text" not in line.fields
        for name in PACK_FIELDS:
            assert line.fields[name].name == name
            assert line.fields[name].confidence == line.fields["quantity"].confidence == 0.9
        assert Decimal(line.fields["quantity"].value) * Decimal(
            line.fields["unit_price"].value["amount"]
        ) == Decimal(line.fields["line_total"].value["amount"])
    assert result.stated_total is not None
    assert result.stated_total.value == {"amount": total, "currency": "SAR"}
    arithmetic = validate_arithmetic(result)
    assert arithmetic.status == "reconciled"
    assert arithmetic.computed_total == Decimal(total)


@pytest.mark.parametrize("unit", [None, "كيس"])
def test_unparseable_pack_is_kept_for_review(unit: str | None) -> None:
    text = "عبوة غير واضحة"
    result = azure_di._parse_invoice_result(table_payload(text, unit=unit), "layout:test")
    fields = result.lines[0].fields
    assert fields["pack_text"] == ExtractedField("pack_text", text, 0.4)
    assert {"pack_count", "unit_size"}.isdisjoint(fields)
    if unit is None:
        assert "pack_unit" not in fields
    else:
        assert fields["pack_unit"] == ExtractedField("pack_unit", unit, 0.9)
    assert validate_arithmetic(result).status == "reconciled"
    assert (
        _review_reason(result, "reconciled", 0.85, SupplierMatch(None, None, False))
        == "low_confidence"
    )


@pytest.mark.parametrize("text", ["", " \t\n "])
@pytest.mark.parametrize("unit", [None, "كيس"])
def test_blank_pack_is_absent_and_does_not_flag_review(text: str, unit: str | None) -> None:
    result = azure_di._parse_invoice_result(table_payload(text, unit=unit), "layout:test")
    fields = result.lines[0].fields
    assert "pack_text" not in fields
    assert {"pack_count", "unit_size"}.isdisjoint(fields)
    if unit is None:
        assert "pack_unit" not in fields
    else:
        assert fields["pack_unit"] == ExtractedField("pack_unit", unit, 0.9)
    without_pack = azure_di._parse_invoice_result(table_payload(None, unit=unit), "layout:test")
    assert fields == without_pack.lines[0].fields
    assert validate_arithmetic(result).status == "reconciled"
    assert _review_reason(result, "reconciled", 0.85, SupplierMatch(None, None, False)) is None


def test_pack_column_wins_over_unit_column() -> None:
    result = azure_di._parse_invoice_result(
        table_payload("كرتون 12 × 1 لتر", unit="كرتون"), "layout:test"
    )
    fields = result.lines[0].fields
    assert fields["pack_count"].value == 12
    assert fields["unit_size"].value == "1"
    assert fields["pack_unit"].value == "litre"


def test_only_unit_column_keeps_existing_fields() -> None:
    result = azure_di._parse_invoice_result(table_payload(None, unit="كيس"), "layout:test")
    assert result.lines[0].fields == {
        "quantity": ExtractedField("quantity", "2", 0.9),
        "unit_price": ExtractedField("unit_price", {"amount": "85.00", "currency": "SAR"}, 0.9),
        "line_total": ExtractedField("line_total", {"amount": "170.00", "currency": "SAR"}, 0.9),
        "pack_unit": ExtractedField("pack_unit", "كيس", 0.9),
    }
    assert validate_arithmetic(result).status == "reconciled"


def test_pack_fields_share_row_confidence_on_arithmetic_mismatch() -> None:
    result = azure_di._parse_invoice_result(
        table_payload("كيس 10 كجم", total="171.00"), "layout:test"
    )
    fields = result.lines[0].fields
    for name in PACK_FIELDS:
        assert fields[name].confidence == fields["quantity"].confidence == 0.5


def table_payload(pack: str | None, *, unit: str | None = None, total: str = "170.00") -> dict:
    columns = [("الصنف", "أرز بسمتي"), ("الكمية", "2"), ("unit price", "85.00")]
    if pack is not None:
        columns.append(("العبوة", pack))
    if unit is not None:
        columns.append(("الوحدة", unit))
    columns.append(("الإجمالي (ر.س)", total))
    cells = []
    for column, (header, value) in enumerate(columns):
        cells.extend(
            [
                {"rowIndex": 0, "columnIndex": column, "content": header},
                {"rowIndex": 1, "columnIndex": column, "content": value},
            ]
        )
    return {
        "content": f"الإجمالي {total} ر.س",
        "tables": [{"rowCount": 2, "columnCount": len(columns), "cells": cells}],
    }
