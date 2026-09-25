"""Real end-to-end test for R4.3 Phase 6 (T033, US4): a qualifying response captured through
the FULL ingestion path (process_inbound_email(), not a direct service call) auto-prepares a
real purchase request when an enabled guardrail's conditions are met.

`process_inbound_email()` evaluates guardrails against whatever `quotation_line`/`match_decision`
rows exist for the just-captured quotation at the moment of capture -- real extraction/matching is
async and wouldn't have run yet in this synchronous test. To exercise a genuinely qualifying
response without standing up the full extraction pipeline, this test monkeypatches
`orchestrator._insert_quotation` to also insert a line, a match decision, and a prior landed-cost
data point (the price-history baseline) for the same product -- simulating "extraction and
matching already completed for this response" and "the tenant has purchased this product before".
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


@pytest.mark.asyncio
async def test_guardrail_e2e(
    mock_supabase_client: None, monkeypatch: pytest.MonkeyPatch  # noqa: F811
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
                (uuid.uuid4(), "Guardrail Test Product"),
            )
            cur.execute(
                "select id from canonical_product where name = 'Guardrail Test Product'"
            )
            canonical_id = cur.fetchone()[0]
            cur.execute(
                "insert into workspace_product (id, tenant_id, canonical_product_id, "
                "tenant_name) values (%s, %s, %s, %s)",
                (wp_id, tenant_id, canonical_id, "Guardrail Test Product"),
            )
            cur.execute(
                "insert into rfq_line (id, tenant_id, rfq_id, workspace_product_id, quantity) "
                "values (%s, %s, %s, %s, 1)",
                (uuid.uuid4(), tenant_id, rfq_id, wp_id),
            )

            # Prior purchase history for the same product, at 100.00/unit -- the price-variance
            # baseline the guardrail's max_price_variance_pct will check the new quote against.
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
                "values (%s,%s,%s,1,'historical',1,100,'USD')",
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
                "values (%s,%s,%s,%s,1,1,'each',100,'USD',0,'USD',0,'USD',0,'USD',0,'USD',"
                "100,'USD','{}','v1',now())",
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
                    Decimal("1000.00"),
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
        """Stand in for real (async) extraction+matching: give the just-captured quotation one
        line, matched to the same product the RFQ/history above use, at a price within the
        guardrail's variance tolerance of the 100.00 baseline."""
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
                "unit_price_amount, unit_price_currency) "
                "values (%s, %s, %s, 1, 'text', 1, 105, 'USD')",
                (ql_id, tenant_id, qid),
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

    # The guardrail fire calls RequestsService.create_request() over a real PostgREST HTTP
    # call. conftest.py's SUPABASE_SERVICE_ROLE_KEY is a deliberate fake ("...e30.signature",
    # not a real signature), so it can't authenticate against a live stack -- same fix as
    # test_rfq_service_e2e.py's own prepare_request() tests: a psycopg-backed fake client.
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
            assert cur.fetchone()[0] == "converted"

            cur.execute(
                "select purchase_request_id from auto_preparation_event where guardrail_id = %s",
                (guardrail_id,),
            )
            event_row = cur.fetchone()
            assert event_row is not None
            purchase_request_id = event_row[0]
            assert purchase_request_id is not None

            cur.execute(
                "select source_rfq_response_id from purchase_request where id = %s",
                (purchase_request_id,),
            )
            pr_row = cur.fetchone()
            assert pr_row is not None
            assert pr_row[0] is not None

            # FR-014: disabling the guardrail after it fired must not retroactively touch the
            # event or the request it already created.
            cur.execute(
                "update auto_preparation_guardrail set enabled = false where id = %s",
                (guardrail_id,),
            )
            conn.commit()

            cur.execute(
                "select id from auto_preparation_event where guardrail_id = %s", (guardrail_id,)
            )
            assert cur.fetchone() is not None

            cur.execute("select id from purchase_request where id = %s", (purchase_request_id,))
            assert cur.fetchone() is not None
