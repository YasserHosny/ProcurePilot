from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from procurepilot_extraction_worker.azure_di import (
    AzureDocumentIntelligenceProvider,
    _header_role,
    _parse_invoice_result,
)
from procurepilot_extraction_worker.models import ExtractedField
from procurepilot_extraction_worker.settings import WorkerSettings
from procurepilot_extraction_worker.validation import validate_arithmetic
from procurepilot_extraction_worker.worker import (
    SupplierMatch,
    _normalise_pack_unit,
    _review_reason,
)

FIXTURES = Path(__file__).parent / "fixtures" / "azure_layout"
NO_MATCH = SupplierMatch(None, None, False)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize(
    ("text", "role"),
    [
        ("الصنف", "description"),
        ("الصنف والمواصفات", "description"),
        ("الصنف والمواصفات", "description"),
        ("البيان", "description"),
        ("الوصف", "description"),
        ("item", "description"),
        ("description", "description"),
        ("product", "description"),
        ("الكمية", "quantity"),
        ("الكميه", "quantity"),
        ("العدد", "quantity"),
        ("qty", "quantity"),
        ("quantity", "quantity"),
        ("الوحدة", "unit"),
        ("الوحده", "unit"),
        ("unit", "unit"),
        ("uom", "unit"),
        ("سعر الوحدة", "unit_price"),
        ("سعر الوحده", "unit_price"),
        ("السعر", "unit_price"),
        ("الفئة", "unit_price"),
        ("الفئه", "unit_price"),
        ("unit price", "unit_price"),
        ("price", "unit_price"),
        ("rate", "unit_price"),
        ("الإجمالي", "line_total"),
        ("اإلجمايل", "line_total"),
        ("القيمة", "line_total"),
        ("المبلغ", "line_total"),
        ("total", "line_total"),
        ("amount", "line_total"),
        ("اإلجمايل", "line_total"),
        ("اإلجمايل النهايئ", "line_total"),
        ("مرصي", None),
    ],
)
def test_header_keyword_semantics(text: str, role: str | None) -> None:
    assert _header_role(text) == role


@pytest.mark.parametrize("fixture", ["demo-alnour", "demo-alamana"])
@pytest.mark.parametrize(
    "clean,reverse", [(False, False), (True, False), (False, True), (True, True)]
)
def test_demo_rtl_tables_ignore_column_order(fixture: str, clean: bool, reverse: bool) -> None:
    payload = load(f"{fixture}.layout.json")
    cells = payload["tables"][0]["cells"]
    if clean:
        replacements = {
            "اإلجمايل": "الإجمالي",
            "اإلجمايل النهايئ": "الإجمالي النهائي",
            "مرصي": "مصري",
        }
        for cell in cells:
            for bad, good in replacements.items():
                cell["content"] = cell["content"].replace(bad, good)
    if reverse:
        for cell in cells:
            cell["columnIndex"] = (
                payload["tables"][0]["columnCount"]
                - cell["columnIndex"]
                - cell.get("columnSpan", 1)
            )
    result = _parse_invoice_result(payload, "prebuilt-layout:test")
    assert len(result.lines) == result.expected_line_count == 5
    assert all("\n" not in line.original_text for line in result.lines)
    assert result.stated_total.value["amount"] == (
        "56425.00" if fixture == "demo-alnour" else "56925.00"
    )
    assert validate_arithmetic(result).status == "reconciled"


def test_alnour_lines_reconcile_and_can_auto_accept() -> None:
    result = _parse_invoice_result(load("demo-alnour.layout.json"), "layout:test")
    assert [line.fields["quantity"].value for line in result.lines] == [
        "10",
        "20",
        "10",
        "15",
        "50",
    ]
    assert [line.fields["unit_price"].value["amount"] for line in result.lines] == [
        "1680.00",
        "940.00",
        "905.00",
        "545.00",
        "72.00",
    ]
    assert all(line.fields["unit_price"].value["currency"] == "EGP" for line in result.lines)
    assert validate_arithmetic(result).status == "reconciled"
    assert _review_reason(result, "reconciled", 0.85, SupplierMatch("supplier", 1, True)) is None


@pytest.mark.parametrize("repeat_header", [True, False])
def test_alnour_split_tables_accumulate_rows_and_total(repeat_header: bool) -> None:
    payload = split_alnour_tables(repeat_header=repeat_header)
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == result.expected_line_count == 5
    assert result.stated_total.value["amount"] == "56425.00"
    assert validate_arithmetic(result).status == "reconciled"


def test_alnour_split_table_with_different_column_count_is_ignored() -> None:
    payload = split_alnour_tables(repeat_header=False)
    payload["tables"][1]["columnCount"] -= 1
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == 3
    assert result.stated_total is not None
    assert result.expected_line_count == 3
    assert validate_arithmetic(result).status == "mismatch"
    assert _review_reason(result, "mismatch", 0.85, SupplierMatch("supplier", 1, True)) is not None


def test_split_table_page_subtotal_does_not_override_final_grand_total() -> None:
    payload = split_alnour_tables(repeat_header=False, first_page_subtotal=True)
    result = _parse_invoice_result(payload, "layout:test")
    assert len(result.lines) == result.expected_line_count == 5
    assert result.stated_total.value["amount"] == "56425.00"
    assert validate_arithmetic(result).status == "reconciled"


def split_alnour_tables(*, repeat_header: bool, first_page_subtotal: bool = False) -> dict:
    payload = load("demo-alnour.layout.json")
    original = payload["tables"][0]
    first_rows = {0, 1, 2, 3}
    second_rows = {4, 5, 6}
    first = {**original, "rowCount": max(first_rows) + 1}
    first["cells"] = [c.copy() for c in original["cells"] if c["rowIndex"] in first_rows]
    second = {**original, "rowCount": max(second_rows) + 1}
    second_cells = []
    for cell in original["cells"]:
        row = cell["rowIndex"]
        include = row in {4, 5, 6}
        if repeat_header and row == 0:
            include = True
        if first_page_subtotal and row == 0:
            include = False
        if include:
            copied = cell.copy()
            copied["rowIndex"] = row - 3 if row >= 4 else 0
            second_cells.append(copied)
    second["cells"] = second_cells
    if first_page_subtotal:
        subtotal = sum(Decimal(value) for value in ("16800", "18800", "9050"))
        first["cells"].extend(
            [
                {
                    "rowIndex": 4,
                    "columnIndex": 0,
                    "content": f"{subtotal:,.2f}",
                    "rowSpan": 1,
                    "columnSpan": 1,
                },
                {
                    "rowIndex": 4,
                    "columnIndex": 4,
                    "content": "الإجمالي",
                    "rowSpan": 1,
                    "columnSpan": 2,
                },
            ]
        )
        first["rowCount"] = 5
    payload["tables"] = [first, second]
    return payload


def test_amana_delivery_fee_is_counted_once() -> None:
    result = _parse_invoice_result(load("demo-alamana.layout.json"), "layout:test")
    assert len(result.lines) == 5
    assert result.lines[-1].fields["delivery_fee"].value == {"amount": "250.00", "currency": "EGP"}
    assert validate_arithmetic(result).computed_total == Decimal("56925.00")
    assert validate_arithmetic(result).status == "reconciled"


def test_merged_cell_total_is_read_from_any_column_without_paragraph_help() -> None:
    payload = load("demo-alnour.layout.json")
    payload["content"] = ""
    payload["paragraphs"] = []
    result = _parse_invoice_result(payload, "layout:test")
    assert result.stated_total.value["amount"] == "56425.00"


def test_printed_line_total_mismatch_lowers_line_confidence() -> None:
    payload = load("demo-alnour.layout.json")
    for cell in payload["tables"][0]["cells"]:
        if cell["rowIndex"] == 1 and cell["columnIndex"] == 0:
            cell["content"] = "16,801.00"
    result = _parse_invoice_result(payload, "layout:test")
    assert result.lines[0].fields["line_total"].value["amount"] == "16801.00"
    assert result.lines[0].fields["unit_price"].confidence < 0.85


def test_before_tax_total_takes_precedence_over_later_grand_total() -> None:
    payload = load("q1-arabic-western-digits-gm.layout.json")
    table = payload["tables"][0]
    row = table["rowCount"]
    table["rowCount"] += 1
    table["cells"].extend(
        [
            {
                "rowIndex": row,
                "columnIndex": 0,
                "content": "99,999.00",
                "rowSpan": 1,
                "columnSpan": 1,
            },
            {
                "rowIndex": row,
                "columnIndex": 3,
                "content": "الإجمالي النهائي",
                "rowSpan": 1,
                "columnSpan": 1,
            },
        ]
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert result.stated_total.value["amount"] == "16012.50"


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("q1-arabic-western-digits-gm", "16012.50"),
        ("q2-arabic-indic-digits-geneih", "3185.00"),
        ("q3-english-le-marker", "5303.00"),
        ("q4-no-currency-marker", "6771.00"),
        ("q5-mixed-markers", "3200.00"),
    ],
)
def test_pp3_layout_values(fixture: str, expected: str) -> None:
    result = _parse_invoice_result(load(f"{fixture}.layout.json"), "layout:test")
    assert result.stated_total.value["amount"] == expected
    if fixture in (
        "q1-arabic-western-digits-gm",
        "q2-arabic-indic-digits-geneih",
        "q3-english-le-marker",
    ):
        assert result.header["currency"].value == "EGP"
        assert validate_arithmetic(result).status == "reconciled"
    if fixture == "q4-no-currency-marker":
        assert "currency" not in result.header
    if fixture == "q5-mixed-markers":
        assert "currency" not in result.header
        assert all(line.fields["unit_price"].value["currency"] is None for line in result.lines)
    assert (
        _review_reason(result, validate_arithmetic(result).status, 0.85, NO_MATCH) is not None
    ) == (fixture in ("q4-no-currency-marker", "q5-mixed-markers"))


def test_invoice_only_failure_is_merged_line_review() -> None:
    result = _parse_invoice_result(load("demo-alnour.invoice.json"), "invoice:test")
    assert len(result.lines) == 1
    assert result.stated_total.value == {"amount": "56425.00", "currency": "EGP"}
    assert _review_reason(result, "not_applicable", 0.85, NO_MATCH) == "merged_line_items"


def test_table_beats_collapsed_invoice_items_with_fake_client() -> None:
    class Poller:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def result(self) -> dict:
            return self.payload

    class FakeClient:
        def begin_analyze_document(self, model: str, request: object) -> Poller:
            return Poller(
                load(
                    "demo-alnour.invoice.json"
                    if model == "prebuilt-invoice"
                    else "demo-alnour.layout.json"
                )
            )

    settings = WorkerSettings("", "", "")
    result = AzureDocumentIntelligenceProvider(settings, client=FakeClient()).extract(
        document_id="doc",
        mime_type="application/pdf",
        storage_path="unused",
        document_bytes=b"fixture",
    )
    assert len(result.lines) == 5
    assert result.model_version == "prebuilt-layout:2024-11-30"


def test_layout_falls_back_to_invoice_total_and_keeps_header_fields() -> None:
    class Poller:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def result(self) -> dict:
            return self.payload

    invoice = load("demo-alnour.invoice.json")
    invoice["documents"][0]["fields"]["InvoiceTotal"]["content"] = "57,000.00 ج.م"
    invoice["documents"][0]["fields"]["InvoiceDate"] = {
        "content": "16/10/2026",
        "confidence": 0.9,
    }
    layout = load("demo-alnour.layout.json")
    table = layout["tables"][0]
    total_row = table["rowCount"] - 1
    table["cells"] = [c for c in table["cells"] if c["rowIndex"] != total_row]
    layout["paragraphs"] = []
    layout["content"] = ""

    class FakeClient:
        def begin_analyze_document(self, model: str, request: object) -> Poller:
            return Poller(invoice if model == "prebuilt-invoice" else layout)

    result = AzureDocumentIntelligenceProvider(
        WorkerSettings("", "", ""), client=FakeClient()
    ).extract(
        document_id="doc",
        mime_type="application/pdf",
        storage_path="unused",
        document_bytes=b"fixture",
    )
    assert result.stated_total.value["amount"] == "57000.00"
    assert "supplier_name" in result.header
    assert "issue_date" in result.header


@pytest.mark.parametrize(
    ("description", "qty", "price"),
    [("Total Clean Detergent 5L", "3", "40"), ("خدمة توصيل", "2", "50")],
)
def test_item_labels_are_not_classified_as_totals_or_charges(
    description: str, qty: str, price: str
) -> None:
    payload = load("q3-english-le-marker.layout.json")
    table = payload["tables"][0]
    table["cells"] = [c for c in table["cells"] if c["rowIndex"] != 1]
    table["cells"].extend(
        [
            {"rowIndex": 1, "columnIndex": 0, "content": "120.00", "rowSpan": 1, "columnSpan": 1},
            {"rowIndex": 1, "columnIndex": 1, "content": price, "rowSpan": 1, "columnSpan": 1},
            {"rowIndex": 1, "columnIndex": 2, "content": qty, "rowSpan": 1, "columnSpan": 1},
            {
                "rowIndex": 1,
                "columnIndex": 3,
                "content": description,
                "rowSpan": 1,
                "columnSpan": 1,
            },
        ]
    )
    result = _parse_invoice_result(payload, "layout:test")
    assert any(line.original_text == description for line in result.lines)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("كجم", "kilogram"),
        ("كيلو", "kilogram"),
        ("جم", "gram"),
        ("جرام", "gram"),
        ("لتر", "litre"),
        ("مل", "millilitre"),
        ("صفيحة", "each"),
        ("شيكارة", "each"),
        ("كرتونة", "each"),
        ("علبة", "each"),
        ("كيس", "each"),
        ("قطعة", "each"),
        ("عبوة", "each"),
    ],
)
def test_arabic_pack_unit_aliases(raw: str, expected: str) -> None:
    assert _normalise_pack_unit(raw) == expected


def test_structured_parse_without_total_keeps_existing_auto_accept_policy() -> None:
    from procurepilot_extraction_worker.models import ExtractedLine, ExtractionResult

    result = ExtractionResult(
        "structured_parse",
        "test",
        {"currency": ExtractedField("currency", "EGP", 1)},
        [
            ExtractedLine(
                1,
                "item",
                {
                    "quantity": ExtractedField("quantity", "1", 1),
                    "unit_price": ExtractedField(
                        "unit_price", {"amount": "2", "currency": "EGP"}, 1
                    ),
                },
            )
        ],
    )
    assert _review_reason(result, "not_applicable", 0.85, NO_MATCH) is None
