"""Database-backed owner explanations for RFQ guardrails."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.test_rfq_guardrail_deferred import _baseline_and_guardrail
from integration.test_rfq_service_e2e import (
    _patch_requests_service_for_test,
    _seed_rfq_and_responses,
    _seed_tenant,
)
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import _evaluate_guardrails_for_rfq
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs Postgres with the migrations applied",
)


def _member(tenant_id: UUID, user_id: UUID, membership_id: UUID, role: MemberRole) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email=f"{role.value}-{uuid4().hex}@example.test",
        role=role,
    )


def _complete_second_response(cur: psycopg.Cursor, response_id: UUID, product_id: UUID) -> None:
    cur.execute(
        "select quotation_id from rfq_response where id = %s",
        (response_id,),
    )
    quotation_id = cur.fetchone()[0]
    cur.execute(
        "select id from quotation_line where quotation_id = %s and line_number = 2",
        (quotation_id,),
    )
    line_id = cur.fetchone()[0]
    cur.execute(
        "insert into match_decision "
        "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
        "is_automatic,confidence) "
        "select %s,tenant_id,%s,%s,'no_match_new_product',true,1 "
        "from quotation_line where id = %s",
        (uuid4(), line_id, product_id, line_id),
    )


def _seed_explanation_fixture() -> tuple[UUID, UUID, UUID, UUID, UUID, UUID, UUID, UUID]:
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"explanations-{uuid4().hex}"
            )
            rfq_id, response_a, response_b, branch_id = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            guardrail_id, products = _baseline_and_guardrail(
                cur,
                tenant_id=tenant_id,
                membership_id=membership_id,
                rfq_id=rfq_id,
            )
            _complete_second_response(cur, response_b, products[1])
            # The helper creates the guardrail after the response rows for convenience. Make the
            # persisted timestamp reflect the production order: guardrail first, responses after.
            cur.execute(
                "update auto_preparation_guardrail set created_at = now() - interval '1 hour' "
                "where id = %s",
                (guardrail_id,),
            )
        conn.commit()
    return (
        tenant_id,
        user_id,
        membership_id,
        rfq_id,
        response_a,
        response_b,
        guardrail_id,
        products[1],
    )


def _reasons(service: RfqService, member: CurrentMember, rfq_id: UUID) -> dict[UUID, str]:
    result = service.list_responses(member=member, rfq_id=rfq_id)
    return {
        UUID(item.id) if isinstance(item.id, str) else item.id: item.guardrail_evaluations[0].reason
        for item in result.items
    }


def test_owner_explanations_are_real_read_only_snapshots_and_update_after_firing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        tenant_id,
        user_id,
        membership_id,
        rfq_id,
        response_a,
        response_b,
        guardrail_id,
        _product_id,
    ) = _seed_explanation_fixture()
    owner = _member(tenant_id, user_id, membership_id, MemberRole.owner)
    service = RfqService(get_settings())

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s",
                (tenant_id,),
            )
            event_count = cur.fetchone()[0]
            cur.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (tenant_id,),
            )
            request_count = cur.fetchone()[0]
            cur.execute("select count(*) from audit_event where tenant_id = %s", (tenant_id,))
            audit_count = cur.fetchone()[0]
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            status_before = cur.fetchone()[0]

    before = _reasons(service, owner, rfq_id)
    assert before[response_a] == "would_fire"
    assert before[response_b] == "not_lowest_price"

    # A second owner read must not create an event, request, audit row, or status transition.
    assert _reasons(service, owner, rfq_id) == before
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s",
                (tenant_id,),
            )
            assert cur.fetchone()[0] == event_count
            cur.execute(
                "select count(*) from purchase_request where tenant_id = %s",
                (tenant_id,),
            )
            assert cur.fetchone()[0] == request_count
            cur.execute("select count(*) from audit_event where tenant_id = %s", (tenant_id,))
            assert cur.fetchone()[0] == audit_count
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == status_before == "responded"

    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        _evaluate_guardrails_for_rfq(get_settings(), conn, tenant_id=tenant_id, rfq_id=rfq_id)

    after = _reasons(service, owner, rfq_id)
    assert after[response_a] == "fired"
    assert after[response_b] == "rfq_not_open"
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from auto_preparation_event "
                "where tenant_id = %s and guardrail_id = %s",
                (tenant_id, guardrail_id),
            )
            assert cur.fetchone()[0] == 1


def test_pending_response_explanation_is_owner_only_and_cross_tenant_guardrails_do_not_leak(
) -> None:
    tenant_id, user_id, membership_id, rfq_id, response_a, response_b, _guardrail_id, _ = (
        _seed_explanation_fixture()
    )
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("select quotation_id from rfq_response where id = %s", (response_b,))
            quotation_id = cur.fetchone()[0]
            cur.execute("update quotation set status = 'in_review' where id = %s", (quotation_id,))
            other_tenant, _other_user, other_membership = _seed_tenant(
                cur, email_suffix=f"other-{uuid4().hex}"
            )
            branch_id = uuid4()
            cur.execute(
                "insert into branch (id,tenant_id,name) values (%s,%s,'Other')",
                (branch_id, other_tenant),
            )
            cur.execute(
                "insert into auto_preparation_guardrail "
                "(id,tenant_id,created_by_membership_id,default_branch_id,max_order_value_amount," 
                "max_order_value_currency,min_response_count,max_price_variance_pct,enabled) "
                "values (%s,%s,%s,%s,999,'GBP',1,0.1,true)",
                (uuid4(), other_tenant, other_membership, branch_id),
            )
        conn.commit()

    service = RfqService(get_settings())
    owner_reasons = _reasons(
        service, _member(tenant_id, user_id, membership_id, MemberRole.owner), rfq_id
    )
    assert owner_reasons[response_a] == "responses_pending"
    assert owner_reasons[response_b] == "responses_pending"
    assert len(owner_reasons) == 2


def test_buyer_receives_the_same_guardrail_explanations_as_owner() -> None:
    tenant_id, owner_user_id, owner_membership, rfq_id, _a, _b, _g, _ = _seed_explanation_fixture()
    buyer_user_id, buyer_membership = uuid4(), uuid4()
    email = f"buyer-{uuid4().hex}@example.test"
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (buyer_user_id, email))
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'buyer',false)",
                (buyer_membership, tenant_id, buyer_user_id, email),
            )
        conn.commit()

    service = RfqService(get_settings())
    owner_results = service.list_responses(
        member=_member(tenant_id, owner_user_id, owner_membership, MemberRole.owner),
        rfq_id=rfq_id,
    )
    buyer_results = service.list_responses(
        member=_member(tenant_id, buyer_user_id, buyer_membership, MemberRole.buyer),
        rfq_id=rfq_id,
    )
    owner_evaluations = {item.id: item.guardrail_evaluations for item in owner_results.items}
    buyer_evaluations = {item.id: item.guardrail_evaluations for item in buyer_results.items}
    assert buyer_evaluations == owner_evaluations
    assert all(item.guardrail_evaluations for item in buyer_results.items)
