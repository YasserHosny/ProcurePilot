from __future__ import annotations

import sys
from pathlib import Path

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    ensure_quotation_reference_data,
    make_document,
    make_quotation,
)

WORKER_SRC = Path(__file__).resolve().parents[4] / "services" / "extraction-worker" / "src"
sys.path.insert(0, str(WORKER_SRC))

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for arithmetic mismatch integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_mismatched_quotations_always_create_mandatory_review_task(conn: object) -> None:
    from procurepilot_extraction_worker.models import (
        ExtractedField,
        ExtractedLine,
        ExtractionResult,
    )
    from procurepilot_extraction_worker.validation import validate_arithmetic
    from procurepilot_extraction_worker.worker import (
        SupplierMatch,
        _persist_result,
        _update_quotation_status,
    )

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "arithmetic-mismatch")
        ensure_quotation_reference_data(cur)
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(cur, workspace, document_id=document_id, status="extracting")
        result = ExtractionResult(
            method="bedrock",
            model_version="stub-provider-v1",
            header={"currency": ExtractedField("currency", "GBP", 0.9900)},
            lines=[
                ExtractedLine(
                    1,
                    "High confidence line",
                    {
                        "quantity": ExtractedField("quantity", "2", 0.9900),
                        "unit_price": ExtractedField(
                            "unit_price",
                            {"amount": "10.00", "currency": "GBP"},
                            0.9900,
                        ),
                    },
                )
            ],
            stated_total=ExtractedField(
                "stated_total",
                {"amount": "25.00", "currency": "GBP"},
                0.9900,
            ),
        )
        arithmetic = validate_arithmetic(result)

        _persist_result(conn, workspace.tenant_id, quotation_id, result, arithmetic.status)
        _update_quotation_status(
            conn,
            quotation_id,
            "in_review",
            arithmetic.status,
            result,
            SupplierMatch(None, None, had_candidates=False),
        )

        act_as(cur, workspace)
        cur.execute("select arithmetic_status from quotation where id = %s", (quotation_id,))
        assert cur.fetchone() == ("mismatch",)
        cur.execute(
            "select status, priority, reason from review_task where quotation_id = %s",
            (quotation_id,),
        )
        assert cur.fetchone() == ("open", "high", "arithmetic_mismatch")
