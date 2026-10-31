import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from procurepilot_extraction_worker.azure_di import _parse_invoice_result
from procurepilot_extraction_worker.settings import WorkerSettings
from procurepilot_extraction_worker.validation import validate_arithmetic
from procurepilot_extraction_worker.worker import (
    SupplierMatch,
    _extract,
    _persist_result,
    _review_reason,
    _update_quotation_status,
)


def _payload(name: str) -> dict[str, object]:
    prices, total = (
        (["86", "150", "38", "82"], "4830")
        if name == "dhahabi"
        else (["88", "146", "36", "85"], "4855")
    )
    rows = [["الصنف", "الكمية", "سعر الوحدة", "الإجمالي"]]
    rows.extend(
        [
            [desc, qty, price, str(Decimal(qty) * Decimal(price))]
            for desc, qty, price in zip(
                ["أرز بسمتي", "زيت دوار الشمس", "سكر أبيض", "دقيق"],
                ["20", "10", "10", "15"],
                prices,
                strict=True,
            )
        ]
    )
    cells = [
        {"rowIndex": r, "columnIndex": c, "columnSpan": 1, "content": text}
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    cells.extend(
        [
            {
                "rowIndex": 5,
                "columnIndex": 0,
                "columnSpan": 3,
                "content": "الإجمالي شامل ضريبة القيمة المضافة 15%",
            },
            {"rowIndex": 5, "columnIndex": 3, "content": total + " ر.س"},
        ]
    )
    return {
        "content": (Path(__file__).parent / "fixtures" / f"{name}-vat-inclusive.txt").read_text(),
        "tables": [{"columnCount": 4, "rowCount": 6, "cells": cells}],
    }


def _extract_payload(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> object:
    from procurepilot_extraction_worker import worker
    from procurepilot_extraction_worker.azure_di import AzureDocumentIntelligenceProvider

    monkeypatch.setattr(worker, "_download_storage_object", lambda *a, **kw: b"unused")
    monkeypatch.setattr(
        AzureDocumentIntelligenceProvider,
        "extract",
        lambda *a, **kw: _parse_invoice_result(payload, "layout:test"),
    )
    return _extract(
        WorkerSettings(
            database_url=os.environ["TEST_DATABASE_URL"],
            supabase_url="http://unused",
            supabase_service_role_key="unused",
            provider_mode="azure_di",
        ),
        document_id=uuid4(),
        document={
            "mime_type": "application/pdf",
            "storage_path": "unused",
            "storage_bucket": "unused",
        },
    )


@pytest.mark.parametrize("name", ["dhahabi", "wafra"])
def test_real_arabic_quotes_detect_reviewable_vat_basis(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    result = _extract_payload(monkeypatch, _payload(name))
    assert result.header["prices_include_vat"].value is True
    assert result.header["vat_rate"].value == "0.15"
    assert (
        result.header["prices_include_vat"].confidence
        == result.header["vat_rate"].confidence
        == 0.80
    )
    assert validate_arithmetic(result).status == "reconciled"
    assert (
        _review_reason(result, "reconciled", 0.85, SupplierMatch(None, None, False))
        == "low_confidence"
    )


@pytest.mark.parametrize(
    "statement,expected",
    [("Prices include VAT 15%", True), ("Total incl. VAT 15%", False), ("No VAT statement", None)],
)
def test_english_and_exclusive_quotes(
    monkeypatch: pytest.MonkeyPatch, statement: str, expected: bool | None
) -> None:
    payload = _payload("dhahabi")
    payload["content"] = statement + " SAR"
    table = payload["tables"][0]
    for cell in table["cells"]:
        if cell["rowIndex"] == 5:
            cell["content"] = (
                "Total"
                if cell["columnIndex"] == 0
                else ("5554.50 SAR" if expected is False else "4830 SAR")
            )
    if expected is False:
        table["cells"].extend(
            [
                {"rowIndex": 6, "columnIndex": 0, "columnSpan": 3, "content": "VAT 15%"},
                {"rowIndex": 6, "columnIndex": 3, "content": "724.50 SAR"},
            ]
        )
        table["rowCount"] = 7
    result = _extract_payload(monkeypatch, payload)
    if expected is None:
        assert "prices_include_vat" not in result.header
        assert "vat_rate" not in result.header
    else:
        assert result.header["prices_include_vat"].value is expected
        assert result.header["vat_rate"].value == "0.15"


def test_structured_parser_carries_cell_text_to_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_extraction_worker import worker

    content = (
        b"currency,description,quantity,unit_price,stated_total,notes\n"
        b"SAR,Rice,100,13.80,1380,Prices include VAT 15%\n"
    )
    monkeypatch.setattr(worker, "_download_storage_object", lambda *a, **kw: content)
    result = _extract(
        WorkerSettings(
            database_url=os.environ["TEST_DATABASE_URL"],
            supabase_url="http://unused",
            supabase_service_role_key="unused",
        ),
        document_id=uuid4(),
        document={"mime_type": "text/csv", "storage_path": "unused", "storage_bucket": "unused"},
    )
    assert result.header["prices_include_vat"].value is True
    assert validate_arithmetic(result).status == "reconciled"


def test_document_rate_persists_only_on_lines_without_own_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_extraction_worker import db

    result = _extract_payload(monkeypatch, _payload("dhahabi"))
    from dataclasses import replace

    from procurepilot_extraction_worker.models import ExtractedField

    first = result.lines[0]
    first = replace(
        first, fields={**first.fields, "vat_rate": ExtractedField("vat_rate", "0.05", 0.99)}
    )
    result = replace(result, lines=[first, *result.lines[1:]])
    with db.connect(os.environ["TEST_DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            user, tenant, member, invitation, doc, quote = [uuid4() for _ in range(6)]
            email = f"vat-{user}@example.test"
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (user, email))
            cur.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at) "
                "values (%s,%s,%s,now()+interval '7 days')",
                (invitation, email, str(invitation)),
            )
            cur.execute(
                "insert into tenant (id,name,slug,region,currency,tax_model,"
                "platform_invitation_id) values (%s,'VAT test',%s,'GB','GBP','uk_vat',%s)",
                (tenant, str(tenant), invitation),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (member, tenant, user, email),
            )
            cur.execute(
                "insert into document (id,tenant_id,storage_bucket,storage_path,mime_type,"
                "created_by) values (%s,%s,'quotations',%s,'application/pdf',%s)",
                (doc, tenant, f"tenants/{tenant}/quotations/{doc}/quote.pdf", member),
            )
            cur.execute(
                "insert into quotation (id,tenant_id,document_id,status) "
                "values (%s,%s,%s,'extracting')",
                (quote, tenant, doc),
            )
        _persist_result(conn, tenant, quote, result, "reconciled")
        _update_quotation_status(
            conn, quote, "in_review", "reconciled", result, SupplierMatch(None, None, False), {}
        )
        with conn.cursor() as cur:
            cur.execute("select prices_include_vat from quotation where id=%s", (quote,))
            assert cur.fetchone() == (True,)
            cur.execute(
                "select vat_rate from quotation_line where quotation_id=%s order by line_number",
                (quote,),
            )
            assert [row[0] for row in cur.fetchall()] == [Decimal("0.05"), *[Decimal("0.15")] * 3]
            cur.execute(
                "select count(*) from field_extraction where quotation_id=%s "
                "and entity_type='quotation_line' and field_name='vat_rate'",
                (quote,),
            )
            assert cur.fetchone() == (1,)
        conn.rollback()
