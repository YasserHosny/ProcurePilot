"""Real end-to-end test for R4.3 Phase 6 (T033, US4): a qualifying response captured through
the FULL ingestion path (process_inbound_email(), not a direct service call) auto-prepares a
real purchase request when an enabled guardrail's conditions are met.

The reply is captured first with no extracted lines. Extraction, review, matching, and worker
evaluation are then simulated in their production order.
"""

import json
import os
import sys
import uuid
from decimal import Decimal

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.shared.mailer import FakeMailer

sys.path.append(os.path.dirname(__file__))
from test_rfq_response_capture import (  # noqa: E402, F401
    _create_email_bytes,
    _seed_rfq_with_recipient,
    _seed_tenant_and_supplier,
    mock_supabase_client,
)
from test_rfq_service_e2e import _patch_requests_service_for_test  # noqa: E402

from procurepilot_api.modules.ingestion.guardrail_jobs import enqueue_guardrail_evaluation
from procurepilot_api.workers.email_ingestion_worker import _process_job


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

            # Finding 38b: the guardrail's default cost centre (on its default branch) must land
            # on the prepared request.
            cost_centre_id = uuid.uuid4()
            cur.execute(
                "insert into cost_centre (id, tenant_id, name, code, branch_id) "
                "values (%s, %s, 'Kitchen', %s, %s)",
                (cost_centre_id, tenant_id, f"CC-{cost_centre_id.hex[:8]}", branch_id),
            )

            guardrail_id = uuid.uuid4()
            cur.execute(
                "insert into auto_preparation_guardrail "
                "(id, tenant_id, created_by_membership_id, default_branch_id, "
                "default_cost_centre_id, "
                "max_order_value_amount, max_order_value_currency, min_response_count, "
                "max_price_variance_pct, enabled) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    guardrail_id,
                    tenant_id,
                    membership_id,
                    branch_id,
                    cost_centre_id,
                    Decimal("1000.00"),
                    "USD",
                    1,
                    Decimal("0.10"),
                    True,
                ),
            )
        conn.commit()

    # The guardrail fire calls RequestsService.create_request() over a real PostgREST HTTP
    # call. conftest.py's SUPABASE_SERVICE_ROLE_KEY is a deliberate fake ("...e30.signature",
    # not a real signature), so it can't authenticate against a live stack -- same fix as
    # test_rfq_service_e2e.py's own prepare_request() tests: a psycopg-backed fake client.
    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )
    # The owner is told by email; RFQ_MAILER_MODE is stub here, so it lands in FakeMailer.
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")
    FakeMailer.clear()

    email_bytes = _create_email_bytes(f"<{uuid.uuid4()}@mail.com>", in_reply_to=msg_id)
    result = process_inbound_email(
        settings, tenant_id=tenant_id, raw_email_bytes=email_bytes, raw_email_ref="s3://path"
    )

    assert result["status"] == "completed"
    quotation_id = uuid.UUID(str(result["quotation_id"]))

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "responded"
            cur.execute(
                "insert into quotation_line "
                "(id, tenant_id, quotation_id, line_number, original_text, quantity, "
                "unit_price_amount, unit_price_currency) "
                "values (%s, %s, %s, 1, 'text', 1, 105, 'USD') returning id",
                (uuid.uuid4(), tenant_id, quotation_id),
            )
            ql_id = cur.fetchone()[0]
            cur.execute("update quotation set status = 'reviewed' where id = %s", (quotation_id,))
            cur.execute(
                "insert into match_decision "
                "(id, tenant_id, quotation_line_id, matched_workspace_product_id, outcome, "
                "is_automatic, confidence) values "
                "(%s, %s, %s, %s, 'no_match_new_product', true, 1.0)",
                (uuid.uuid4(), tenant_id, ql_id, wp_id),
            )
            conn.commit()

    enqueue_guardrail_evaluation(settings, tenant_id=tenant_id, quotation_id=quotation_id)
    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, tenant_id, job_type, status, payload, attempts, max_attempts "
                "from ingestion_jobs where tenant_id = %s and job_type = 'guardrail_eval' "
                "order by created_at desc limit 1",
                (tenant_id,),
            )
            job = dict(
                zip(
                    (
                        "id",
                        "tenant_id",
                        "job_type",
                        "status",
                        "payload",
                        "attempts",
                        "max_attempts",
                    ),
                    cur.fetchone(),
                    strict=True,
                )
            )
    assert _process_job(settings, job) == "completed"

    with psycopg.connect(test_db) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")

            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "converted"

            cur.execute(
                "select purchase_request_id, rfq_id, supplier_id from auto_preparation_event "
                "where guardrail_id = %s",
                (guardrail_id,),
            )
            event_row = cur.fetchone()
            assert event_row is not None
            purchase_request_id = event_row[0]
            assert purchase_request_id is not None
            assert event_row[1] == rfq_id
            assert event_row[2] == supplier_id

            cur.execute(
                "select source_rfq_response_id, cost_centre_id, branch_id "
                "from purchase_request where id = %s",
                (purchase_request_id,),
            )
            pr_row = cur.fetchone()
            assert pr_row is not None
            assert pr_row[0] is not None
            assert pr_row[1] == cost_centre_id
            assert pr_row[2] == branch_id

            # Finding 38a: the guardrail's owner gets one email linking to the draft.
            cur.execute("select email from membership where id = %s", (membership_id,))
            owner_email = cur.fetchone()[0]
            owner_mail = [m for m in FakeMailer.sent_messages if m.to == owner_email]
            assert len(owner_mail) == 1
            assert "Supplier Capture" in owner_mail[0].subject
            assert f"/requests/{purchase_request_id}" in owner_mail[0].body
            # No push is queued: the push sender is still a stub that never delivers.
            cur.execute(
                "select count(*) from push_notification where purchase_request_id = %s",
                (purchase_request_id,),
            )
            assert cur.fetchone()[0] == 0

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

    _assert_provenance_visibility(
        test_db,
        tenant_id=tenant_id,
        branch_id=branch_id,
        purchase_request_id=purchase_request_id,
        guardrail_id=guardrail_id,
        rfq_id=rfq_id,
        supplier_id=supplier_id,
    )


def _member_row(
    cur: psycopg.Cursor, tenant_id: uuid.UUID, role: str
) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, membership_id = uuid.uuid4(), uuid.uuid4()
    email = f"guardrail-{role}-{membership_id}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role),
    )
    return user_id, membership_id


def _member(
    tenant_id: uuid.UUID, user_id: uuid.UUID, membership_id: uuid.UUID, role: MemberRole
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="member@example.test",
        role=role,
    )


def _visible_events(test_db: str, member: CurrentMember, purchase_request_id: uuid.UUID) -> int:
    claims = json.dumps(
        {
            "sub": str(member.user_id),
            "tenant_id": str(member.tenant_id),
            "role": "authenticated",
            "member_role": member.role.value,
        }
    )
    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        conn.execute("set local role authenticated")
        conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
        row = conn.execute(
            "select count(*) from auto_preparation_event where purchase_request_id = %s",
            (purchase_request_id,),
        ).fetchone()
        return int(row[0])


def _assert_provenance_visibility(
    test_db: str,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    purchase_request_id: uuid.UUID,
    guardrail_id: uuid.UUID,
    rfq_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> None:
    """Finding 38a: anyone who can see the prepared request -- including an approver, who has
    no access to the RFQ itself -- sees that a guardrail prepared it and from whose quote. A
    member who cannot see the request, or another workspace, sees neither."""
    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            approver_user, approver_membership = _member_row(cur, tenant_id, "approver")
            fenced_user, fenced_membership = _member_row(cur, tenant_id, "approver")
            other_branch = uuid.uuid4()
            cur.execute(
                "insert into branch (id, tenant_id, name) values (%s, %s, 'Other')",
                (other_branch, tenant_id),
            )
            cur.execute(
                "insert into branch_role_assignment (tenant_id, membership_id, branch_id) "
                "values (%s, %s, %s)",
                (tenant_id, fenced_membership, other_branch),
            )
            other_tenant, _ = _seed_tenant_and_supplier(cur)
            cur.execute(
                "select id, user_id from membership where tenant_id = %s limit 1", (other_tenant,)
            )
            outsider_membership, outsider_user = cur.fetchone()
        conn.commit()

    service = RequestsService(get_settings())
    approver = _member(tenant_id, approver_user, approver_membership, MemberRole.approver)
    seen = service.get_request(
        bearer_token="unused", member=approver, request_id=purchase_request_id
    )
    assert seen.auto_prepared is not None
    assert seen.auto_prepared.guardrail_id == guardrail_id
    assert seen.auto_prepared.rfq_id == rfq_id
    assert seen.auto_prepared.supplier_id == supplier_id
    assert seen.auto_prepared.supplier_name == "Supplier Capture"
    assert _visible_events(test_db, approver, purchase_request_id) == 1

    fenced = _member(tenant_id, fenced_user, fenced_membership, MemberRole.approver)
    with pytest.raises(NotFoundError):
        service.get_request(bearer_token="unused", member=fenced, request_id=purchase_request_id)
    assert _visible_events(test_db, fenced, purchase_request_id) == 0

    outsider = _member(other_tenant, outsider_user, outsider_membership, MemberRole.owner)
    with pytest.raises(NotFoundError):
        service.get_request(bearer_token="unused", member=outsider, request_id=purchase_request_id)
    assert _visible_events(test_db, outsider, purchase_request_id) == 0
