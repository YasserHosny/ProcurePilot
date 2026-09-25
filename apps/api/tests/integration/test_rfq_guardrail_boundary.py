"""R4.3 Final Phase (T043): the Constitution Principle III boundary proof.

Principle III (NON-NEGOTIABLE): "No purchase may be executed without human authorisation, in
any phase, under any configuration." R4.3's guardrails are the first R4.x feature that lets the
SYSTEM itself, not a human, initiate the "prepare" step -- so this is the one release where that
guarantee needs to be executable, not just asserted in the plan's prose.

This test fires a real guardrail through the full ingestion path (mirroring
test_rfq_guardrails_e2e.py's own fixture), then proves, against real Postgres, that the
auto-prepared draft:
  1. Lands in `purchase_request.status = 'draft'` -- never any status past that on its own.
  2. Has no `approval_step` row at all yet -- nothing pre-approved it or skipped the step.
  3. Produced zero `purchase_order` rows anywhere in the tenant -- `purchase_order` is a
     wholly separate table from `purchase_request`, created only by a human action elsewhere
     in this codebase (the `orders` feature); nothing in the RFQ/guardrail code path
     references it at all, and this test confirms that empirically, not just by code review.
  4. Goes through the exact same `submit_request()` -> pending `approval_step` transition a
     manually-created request would -- i.e. the guardrail draft is not exempt from the normal
     human approval pipeline in any way.
"""

import os
import sys
import uuid
from decimal import Decimal

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email
from procurepilot_api.modules.requests.service import RequestsService

sys.path.append(os.path.dirname(__file__))
from test_rfq_response_capture import (  # noqa: E402, F401
    _create_email_bytes,
    _seed_rfq_with_recipient,
    _seed_tenant_and_supplier,
    mock_supabase_client,
)
from test_rfq_service_e2e import _patch_requests_service_for_test  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


@pytest.mark.asyncio
async def test_auto_prepared_draft_never_bypasses_human_approval(
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
                (branch_id, tenant_id, "Boundary Test Branch"),
            )

            cur.execute(
                "select id, user_id from membership where tenant_id = %s limit 1", (tenant_id,)
            )
            membership_id, user_id = cur.fetchone()

            wp_id = uuid.uuid4()
            cur.execute(
                "insert into canonical_product (id, name, base_unit) values (%s, %s, 'each')",
                (uuid.uuid4(), "Boundary Test Product"),
            )
            cur.execute("select id from canonical_product where name = 'Boundary Test Product'")
            canonical_id = cur.fetchone()[0]
            cur.execute(
                "insert into workspace_product (id, tenant_id, canonical_product_id, "
                "tenant_name) values (%s, %s, %s, %s)",
                (wp_id, tenant_id, canonical_id, "Boundary Test Product"),
            )
            cur.execute(
                "insert into rfq_line (id, tenant_id, rfq_id, workspace_product_id, quantity) "
                "values (%s, %s, %s, %s, 1)",
                (uuid.uuid4(), tenant_id, rfq_id, wp_id),
            )

            # Prior purchase history at 100.00/unit, the price-variance baseline.
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

            # Baseline: zero purchase_order rows anywhere in this tenant before the fire.
            cur.execute(
                "select count(*) from purchase_order where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0
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

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")

            cur.execute(
                "select purchase_request_id from auto_preparation_event where guardrail_id = %s",
                (guardrail_id,),
            )
            purchase_request_id = cur.fetchone()[0]
            assert purchase_request_id is not None

            # 1. Never anything past 'draft' on its own.
            cur.execute(
                "select status from purchase_request where id = %s", (purchase_request_id,)
            )
            assert cur.fetchone()[0] == "draft"

            # 2. No approval_step exists yet -- nothing pre-approved or skipped it.
            cur.execute(
                "select count(*) from approval_step where purchase_request_id = %s",
                (purchase_request_id,),
            )
            assert cur.fetchone()[0] == 0

            # 3. Still zero purchase_order rows anywhere in the tenant -- nothing was
            # transmitted to a supplier as a result of this firing.
            cur.execute(
                "select count(*) from purchase_order where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0

        conn.commit()

    # 4. The draft must go through the exact same human submit -> pending-approval transition
    # a manually-created request would -- proving it is not exempt from the approval pipeline.
    member = CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="boundary-owner@example.test",
        role=MemberRole.owner,
    )
    RequestsService(settings).submit_request(
        bearer_token="unused-token", member=member, request_id=purchase_request_id
    )

    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")

            cur.execute(
                "select status from purchase_request where id = %s", (purchase_request_id,)
            )
            assert cur.fetchone()[0] == "submitted"

            cur.execute(
                "select status from approval_step where purchase_request_id = %s",
                (purchase_request_id,),
            )
            step_row = cur.fetchone()
            assert step_row is not None
            assert step_row[0] == "pending"

            # Still no purchase_order -- submission alone never transmits anything either.
            cur.execute(
                "select count(*) from purchase_order where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0
