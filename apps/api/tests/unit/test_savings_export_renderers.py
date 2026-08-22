from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from procurepilot_api.modules.exports.renderers import render_pdf, render_xlsx

openpyxl = pytest.importorskip("openpyxl")
reportlab = pytest.importorskip("reportlab")


def _row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "purchase_record_id": uuid4(),
        "workspace_product_id": uuid4(),
        "supplier_id": uuid4(),
        "recorded_at": datetime.now(UTC),
        "baseline_value_amount": Decimal("100.0000"),
        "baseline_value_currency": "GBP",
        "actual_value_amount": Decimal("88.0000"),
        "actual_value_currency": "GBP",
        "delta_amount": Decimal("12.0000"),
        "delta_currency": "GBP",
    }


def test_xlsx_renderer_contains_money_and_evidence_reference(tmp_path: Path) -> None:
    path = tmp_path / "ledger.xlsx"
    row = _row()
    path.write_bytes(render_xlsx([row]))

    workbook = openpyxl.load_workbook(path)
    values = list(workbook.active.iter_rows(values_only=True))
    # openpyxl pads every row to the sheet's widest row (the 10-column header), so compare only
    # the cells this row actually wrote rather than the full padded tuple.
    assert values[1][:2] == ("Verified rows", 1)
    assert str(row["id"]) in values[4]
    assert "GBP" in values[4]
    assert f"/api/v1/savings/{row['id']}/evidence" in values[4]


def test_xlsx_renderer_makes_intentional_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.xlsx"
    path.write_bytes(render_xlsx([]))

    workbook = openpyxl.load_workbook(path)
    values = list(workbook.active.iter_rows(values_only=True))
    # openpyxl pads every row to the sheet's widest row (the 10-column header), so compare only
    # the cells this row actually wrote rather than the full padded tuple.
    assert values[1][:2] == ("Verified rows", 0)
    assert values[4][0] == "No verified savings matched the requested period."


def test_pdf_renderer_contains_summary_text() -> None:
    content = render_pdf([_row()])
    assert content.startswith(b"%PDF")
    assert b"ProcurePilot" in content


def test_pdf_renderer_makes_intentional_empty_file() -> None:
    content = render_pdf([])
    assert content.startswith(b"%PDF")
    assert b"No verified savings" in content
