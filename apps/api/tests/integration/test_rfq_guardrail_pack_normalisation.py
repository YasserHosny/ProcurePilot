"""Regression test for a real bug found via T047's live walkthrough: guardrail price-variance
evaluation compared a candidate line's raw quotation_line.unit_price_amount (priced per quoted
pack, e.g. per ream) directly against the price-history baseline (priced per normalised base
unit, e.g. per sheet -- the same convention Smart Compare/Savings Ledger/Supplier IQ use
everywhere else in this codebase). For any product whose pack doesn't normalise 1:1, this scale
mismatch made price_variance_exceeded fire on essentially every real quote, silently blocking
guardrail auto-prepare regardless of how reasonable the actual price was. The existing
test_rfq_guardrails_e2e.py never caught this because its seeded product has no pack_definition
row at all (an implicit 1:1 case).

This test seeds a product with a real pack_definition (1 pack = 25 base units) and a price
history baseline consistent with that packing, then a new reply priced consistently with that
same packing (well within variance once normalised) -- and asserts the guardrail fires. Without
the orchestrator.py fix, the raw per-pack price compared against the per-base-unit baseline would
show a >2000% variance and the guardrail would never fire.
"""

import os
import sys
import uuid
from decimal import Decimal

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email

sys.path.append(os.path.dirname(__file__))
from test_rfq_response_capture import (  # noqa: E402, F401
    _create_email_bytes,
    _seed_rfq_with_recipient,
    _seed_tenant_and_supplier,
    mock_supabase_client,
)
from test_rfq_service_e2e import _patch_requests_service_for_test  # noqa: E402


async def _run_guardrail_pack_normalisation_test(
    _mock_supabase_client: None,
    monkeypatch: pytest.MonkeyPatch,
    *,
    line_pack_count: int | None,
    line_unit_size: int | None,
    line_price: int,
) -> None:
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, supplier_id = _seed_tenant_and_supplier(cur)
            rfq_id, rec_id, msg_id = _seed_rfq_with_recipient(cur, tenant_id, supplier_id, "sent")

            branch_id = uuid.uuid4()
            cur.execute(
                "insert into branch (id, tenant_id, name) values (%s, %s, %s)",
                (branch_id, tenant_id, "Test Branch"),
            )
            cur.execute(
                "select id, user_id from membership where tenant_id = %s limit 1", (tenant_id,)
            )
            membership_id, user_id = cur.fetchone()

            wp_id = uuid.uuid4()
            cur.execute(
                "insert into canonical_product (id, name, base_unit) values (%s, %s, 'each')",
                (uuid.uuid4(), "Packed Guardrail Test Product"),
            )
            cur.execute(
                "select id from canonical_product where name = 'Packed Guardrail Test Product'"
            )
            canonical_id = cur.fetchone()[0]
            cur.execute(
                "insert into workspace_product (id, tenant_id, canonical_product_id, "
                "tenant_name) values (%s, %s, %s, %s)",
                (wp_id, tenant_id, canonical_id, "Packed Guardrail Test Product"),
            )
            cur.execute(
                "insert into rfq_line (id, tenant_id, rfq_id, workspace_product_id, quantity) "
                "values (%s, %s, %s, %s, 1)",
                (uuid.uuid4(), tenant_id, rfq_id, wp_id),
            )
            # 1 pack = 25 base units -- a real, non-1:1 pack normalisation. base_quantity is a
            # generated column (pack_count * unit_size); do not insert it explicitly.
            cur.execute(
                "insert into pack_definition "
                "(id, tenant_id, workspace_product_id, pack_count, unit_size) "
                "values (%s, %s, %s, 1, 25)",
                (uuid.uuid4(), tenant_id, wp_id),
            )

            # Price history: 1 pack @ 2500.00 = 100.00 per base unit (the normalised baseline).
            hist_doc_id, hist_quot_id, hist_ql_id, hist_md_id = (
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
            )
            cur.execute(
                "insert into document "
                "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
                "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
                (
                    hist_doc_id,
                    tenant_id,
                    f"tenants/{tenant_id}/quotations/{hist_doc_id}/hist.pdf",
                    f"hash-{hist_doc_id}",
                    membership_id,
                ),
            )
            cur.execute(
                "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
                "values (%s,%s,%s,%s,'USD','reviewed')",
                (hist_quot_id, tenant_id, hist_doc_id, supplier_id),
            )
            cur.execute(
                "insert into quotation_line "
                "(id,tenant_id,quotation_id,line_number,original_text,quantity,"
                "unit_price_amount,unit_price_currency) "
                "values (%s,%s,%s,1,'historical',1,2500,'USD')",
                (hist_ql_id, tenant_id, hist_quot_id),
            )
            cur.execute(
                "insert into match_decision "
                "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
                "is_automatic,confidence) "
                "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                (hist_md_id, tenant_id, hist_ql_id, wp_id),
            )
            cur.execute(
                "insert into landed_cost "
                "(id,tenant_id,quotation_line_id,match_decision_id,quantity,"
                "normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,"
                "vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,"
                "discount_amount,discount_currency,other_charges_amount,other_charges_currency,"
                "total_amount,total_currency,raw_inputs,rule_version,valid_from) "
                "values (%s,%s,%s,%s,1,25,'each',2500,'USD',0,'USD',0,'USD',0,'USD',0,'USD',"
                "2500,'USD','{}','v1',now())",
                (uuid.uuid4(), tenant_id, hist_ql_id, hist_md_id),
            )

            guardrail_id = uuid.uuid4()
            cur.execute(
                "insert into auto_preparation_guardrail "
                "(id, tenant_id, created_by_membership_id, default_branch_id, "
                "max_order_value_amount, max_order_value_currency, min_response_count, "
                "max_price_variance_pct, enabled) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    guardrail_id,
                    tenant_id,
                    membership_id,
                    branch_id,
                    Decimal("10000.00"),
                    "USD",
                    1,
                    Decimal("0.10"),
                    True,
                ),
            )
        conn.commit()

    import procurepilot_api.modules.ingestion.orchestrator as orch

    orig_insert_quotation = orch._insert_quotation

    def fake_insert_quotation(
        conn2: psycopg.Connection,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        supplier_id: uuid.UUID,
        ingestion_email_id: uuid.UUID,
    ) -> uuid.UUID:
        """Insert the new reply line with the pack details for this scenario."""
        qid = orig_insert_quotation(
            conn2,
            tenant_id=tenant_id,
            document_id=document_id,
            supplier_id=supplier_id,
            ingestion_email_id=ingestion_email_id,
        )
        ql_id = uuid.uuid4()
        with conn2.cursor() as cur2:
            cur2.execute(
                "insert into quotation_line "
                "(id, tenant_id, quotation_id, line_number, original_text, quantity, "
                "pack_count, unit_size, unit_price_amount, unit_price_currency) "
                "values (%s, %s, %s, 1, 'text', 1, %s, %s, %s, 'USD')",
                (ql_id, tenant_id, qid, line_pack_count, line_unit_size, line_price),
            )
            cur2.execute(
                "insert into match_decision "
                "(id, tenant_id, quotation_line_id, matched_workspace_product_id, outcome, "
                "is_automatic, confidence) "
                "values (%s, %s, %s, %s, 'no_match_new_product', true, 1.0)",
                (uuid.uuid4(), tenant_id, ql_id, wp_id),
            )
        return qid

    orch._insert_quotation = fake_insert_quotation

    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to=msg_id)
    try:
        result = process_inbound_email(
            settings, tenant_id=tenant_id, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
        )
    finally:
        orch._insert_quotation = orig_insert_quotation

    assert result["status"] == "completed"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")

            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "converted", (
                "guardrail should have fired: normalised price (105/base-unit) is within 10% of "
                "the normalised baseline (100/base-unit) -- if this fails, the pack-normalisation "
                "fix in orchestrator.py's guardrail candidate-line pricing has regressed"
            )

            cur.execute(
                "select purchase_request_id from auto_preparation_event where guardrail_id = %s",
                (guardrail_id,),
            )
            event_row = cur.fetchone()
            assert event_row is not None
            assert event_row[0] is not None


@pytest.mark.asyncio
async def test_guardrail_fires_with_non_unary_pack_normalisation(
    mock_supabase_client: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    await _run_guardrail_pack_normalisation_test(
        mock_supabase_client,
        monkeypatch,
        line_pack_count=None,
        line_unit_size=None,
        line_price=2625,
    )


@pytest.mark.asyncio
async def test_guardrail_prefers_quoted_line_pack_over_catalogue_pack(
    mock_supabase_client: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    await _run_guardrail_pack_normalisation_test(
        mock_supabase_client,
        monkeypatch,
        line_pack_count=1,
        line_unit_size=1,
        line_price=100,
    )
