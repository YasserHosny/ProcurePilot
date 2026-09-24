"""Real (non-mocked) end-to-end test for AnalystService.ask() (R4.2, T013, T019, T021).

Written during orchestrator review of the Phase 3 dispatch: the dispatch's own
integration test (test_analyst_api.py) mocks AnalystService entirely via a FastAPI
dependency override, so it never once exercised service.py's actual SQL against a
real database. This test does — it proves the full round trip (conversation +
turn + citation + audit event, atomically, against real RLS) actually works,
not just that the HTTP layer wires a mock correctly.

T019/T021 (Phase 4, US2/FR-003A) extend this file with the deep-link-to-existing-
surface behaviour: a risky supplier with an existing negotiation brief links to it,
one without a brief links nowhere, a reorder-forecast answer links to the reorder
queue, and a spend/savings answer links to the reports center.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import UUID, uuid4

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.analyst.intent import FakeIntentProvider
from procurepilot_api.modules.analyst.service import AnalystService, get_analyst_service
from procurepilot_api.modules.auth.jwt import MemberRole

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _seed_tenant(cur: psycopg.Cursor, *, email_suffix: str) -> tuple[UUID, UUID, UUID]:
    """One tenant and one owner member — the common base every scenario below extends."""
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    email = f"analyst-e2e-{email_suffix}@example.test"

    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
    )
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, email, f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, "Analyst E2E Ltd", f"analyst-e2e-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, email),
    )
    return tenant_id, user_id, membership_id


def _seed_workspace_with_spend(cur: psycopg.Cursor) -> tuple[UUID, UUID, UUID]:
    """One tenant, one owner member, one purchase order — enough to ground a
    spend_savings question with a real citation."""
    tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="spend")
    supplier_id, order_id = uuid4(), uuid4()

    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, tenant_id, "Analyst E2E Supplier"),
    )
    cur.execute(
        """
        insert into purchase_order
          (id, tenant_id, order_number, supplier_id, status, order_date,
           total_amount, total_currency, tax_amount, tax_currency,
           source_kind, source_reference, created_by)
        values (%s, %s, 'E2E-PO-1', %s, 'received', current_date,
                500.00, 'GBP', 0, 'GBP', 'manual', 'e2e', %s)
        """,
        (order_id, tenant_id, supplier_id, membership_id),
    )
    return tenant_id, user_id, membership_id


def _seed_supplier_with_snapshot(
    cur: psycopg.Cursor,
    tenant_id: UUID,
    membership_id: UUID,
    *,
    supplier_name: str,
    with_negotiation_brief: bool,
) -> UUID:
    """One supplier with a ready, high-risk supplier_scorecard_snapshot (v2 rule), and
    optionally an existing negotiation_brief generated from that snapshot (FR-003A)."""
    supplier_id, snapshot_id = uuid4(), uuid4()
    cur.execute(
        "insert into supplier (id,tenant_id,name) values (%s,%s,%s)",
        (supplier_id, tenant_id, supplier_name),
    )
    cur.execute(
        """
        insert into supplier_scorecard_snapshot
          (id, tenant_id, supplier_id, window_start, window_end, rule_version,
           metrics, risk_score, source_counts, state, confidence, release_posture,
           valid_from, valid_until, source_fingerprint)
        values (%s, %s, %s, current_date - interval '30 days', current_date,
                'supplier-scorecard-v2', '{}'::jsonb, %s::jsonb, '{}'::jsonb,
                'ready', 'high', 'g3_unmet', now(), now() + interval '30 days', %s)
        """,
        (
            snapshot_id,
            tenant_id,
            supplier_id,
            '{"total": 0.8}',
            f"fp-{snapshot_id}",
        ),
    )
    if with_negotiation_brief:
        cur.execute(
            """
            insert into negotiation_brief
              (id, tenant_id, supplier_id, snapshot_id, brief_version, source_fingerprint,
               valid_from, valid_until, created_by_membership_id)
            values (%s, %s, %s, %s, 'brief-v1', %s, now(), now() + interval '30 days', %s)
            """,
            (
                uuid4(),
                tenant_id,
                supplier_id,
                snapshot_id,
                f"brief-fp-{snapshot_id}",
                membership_id,
            ),
        )
    return supplier_id


def _seed_reorder_proposal(cur: psycopg.Cursor, tenant_id: UUID) -> UUID:
    """One workspace product with a ready demand forecast and an open reorder proposal —
    enough to ground a reorder_forecasts question."""
    canonical_id, product_id, forecast_id, proposal_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    cur.execute(
        "insert into canonical_product (id,name,gtin,base_unit) values (%s,%s,null,'litre')",
        (canonical_id, "Analyst E2E Canonical Product"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (product_id, tenant_id, canonical_id, "Analyst E2E Product"),
    )
    today = date.today()
    cur.execute(
        """
        insert into demand_forecast (
          id, tenant_id, workspace_product_id, source_fingerprint, model_version,
          horizon_days, source_window_start, source_window_end, observed_history_days,
          expected_daily_demand, expected_demand, uncertainty_lower, uncertainty_upper,
          stock_on_hand, suggested_quantity, confidence, state, release_posture,
          valid_from, valid_until
        ) values (
          %s, %s, %s, %s, 'forecast-v1', 30, %s, %s, 200,
          1.5, 45.0, 40.0, 50.0, 10.0, 35.0,
          'high', 'ready', 'g3_unmet',
          now(), now() + interval '30 days'
        )
        """,
        (forecast_id, tenant_id, product_id, f"forecast-fp-{forecast_id}", today, today),
    )
    cur.execute(
        """
        insert into reorder_proposal
          (id, tenant_id, demand_forecast_id, workspace_product_id, status)
        values (%s, %s, %s, %s, 'open')
        """,
        (proposal_id, tenant_id, forecast_id, product_id),
    )
    return proposal_id


def _member(
    tenant_id: UUID,
    user_id: UUID,
    membership_id: UUID,
    *,
    role: MemberRole = MemberRole.owner,
    email: str = "analyst-e2e@example.test",
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email=email,
        role=role,
    )


def _seed_additional_member(
    cur: psycopg.Cursor, tenant_id: UUID, *, role: str, email: str
) -> tuple[UUID, UUID]:
    """Add a second (or third) member to an already-seeded tenant — for scoping tests
    that need more than one member in the same workspace."""
    user_id, membership_id = uuid4(), uuid4()
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role),
    )
    return user_id, membership_id


def test_ask_persists_a_real_cited_turn_and_replays_on_idempotency_key() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(
        settings=get_settings(), intent_provider=FakeIntentProvider()
    )
    key = uuid4()

    first = service.ask(
        member=member,
        question_text="How much have we spent this month?",
        idempotency_key=key,
        bearer_token="unused-in-this-path",
    )
    assert len(first.turns) == 1
    turn = first.turns[0]
    assert turn.category.value == "spend_savings"
    assert turn.release_posture == "g3_unmet"
    assert turn.citations, "a grounded spend answer must cite the seeded purchase order"
    assert turn.calculation is not None

    # Replay with the same idempotency key must return the identical turn, not a new one.
    replay = service.ask(
        member=member,
        question_text="How much have we spent this month?",
        idempotency_key=key,
        bearer_token="unused-in-this-path",
    )
    assert replay.id == first.id
    assert len(replay.turns) == 1
    assert replay.turns[0].id == turn.id

    # And the audit event was actually written (FR-012) — not just called.
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from audit_event "
                "where tenant_id = %s and action = 'analyst_turn.created'",
                (tenant_id,),
            )
            row = cur.fetchone()
    assert row is not None
    assert row[0] >= 1, "expected an audit_event row for the created turn"


def test_ask_unsupported_question_returns_explicit_refusal_with_no_citations() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(
        settings=get_settings(), intent_provider=FakeIntentProvider()
    )
    result = service.ask(
        member=member,
        question_text="What's the meaning of life?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    assert len(result.turns) == 1
    turn = result.turns[0]
    assert not turn.citations
    assert "can't answer" in turn.answer_text.lower()


# ---------------------------------------------------------------------------
# Phase 4 (T019/T021): citation resolution and FR-003A next-step links
# ---------------------------------------------------------------------------


def test_citations_resolve_to_real_existing_tenant_records_across_categories() -> None:
    """T019: every citation kind this feature actually produces must point at a real,
    existing row in its source table — not a dangling or fabricated id.

    Scoped to the citation kinds the current retrieval loaders actually emit
    (purchase_order, saving_record, supplier_scorecard_snapshot, reorder_proposal).
    quotation_line, landed_cost, and delivery_receipt are not wired into any
    retrieval loader yet (landed_cost/delivery_receipt aren't wired into any FR-002
    category at all), so there is nothing to seed or assert for them here.
    """
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
            _seed_supplier_with_snapshot(
                cur,
                tenant_id,
                membership_id,
                supplier_name="Citation Check Supplier",
                with_negotiation_brief=False,
            )
            _seed_reorder_proposal(cur, tenant_id)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    scenarios = [
        ("How much have we spent this month?", "purchase_order", "purchase_order"),
        (
            "What is our supplier risk score?",
            "supplier_scorecard_snapshot",
            "supplier_scorecard_snapshot",
        ),
        ("What does our reorder forecast look like?", "reorder_proposal", "reorder_proposal"),
    ]

    for question, expected_kind, table in scenarios:
        result = service.ask(
            member=member,
            question_text=question,
            idempotency_key=uuid4(),
            bearer_token="unused-in-this-path",
        )
        turn = result.turns[-1]
        assert turn.citations, f"expected at least one citation for: {question!r}"
        matching = [c for c in turn.citations if c.source_kind.value == expected_kind]
        assert matching, f"expected a {expected_kind} citation for: {question!r}"

        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                for citation in matching:
                    cur.execute(
                        f"select 1 from {table} where tenant_id = %s and id = %s",  # noqa: S608
                        (tenant_id, citation.source_id),
                    )
                    assert cur.fetchone() is not None, (
                        f"citation {citation.source_id} does not resolve to a real "
                        f"row in {table}"
                    )


def test_next_step_link_points_to_existing_negotiation_brief_when_one_exists() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="brief-yes")
            _seed_supplier_with_snapshot(
                cur,
                tenant_id,
                membership_id,
                supplier_name="Supplier With Brief",
                with_negotiation_brief=True,
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())
    result = service.ask(
        member=member,
        question_text="What is our supplier risk score?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    turn = result.turns[0]
    assert turn.next_step_url is not None
    assert turn.next_step_url.startswith("/negotiation-briefs/")

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            brief_id = turn.next_step_url.removeprefix("/negotiation-briefs/")
            cur.execute(
                "select 1 from negotiation_brief where tenant_id = %s and id = %s",
                (tenant_id, brief_id),
            )
            assert cur.fetchone() is not None, "next_step_url must point at a real brief"


def test_next_step_link_is_absent_when_no_negotiation_brief_exists() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="brief-no")
            _seed_supplier_with_snapshot(
                cur,
                tenant_id,
                membership_id,
                supplier_name="Supplier Without Brief",
                with_negotiation_brief=False,
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())
    result = service.ask(
        member=member,
        question_text="What is our supplier risk score?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    turn = result.turns[0]
    assert turn.next_step_url is None, (
        "must never fabricate a next-step link to a brief that doesn't exist yet"
    )


def test_next_step_link_points_to_reorder_queue_for_reorder_forecast_answers() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix="reorder")
            _seed_reorder_proposal(cur, tenant_id)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())
    result = service.ask(
        member=member,
        question_text="What does our reorder forecast look like?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    turn = result.turns[0]
    assert turn.next_step_url == "/forecasting"


def test_next_step_link_points_to_reports_for_spend_savings_answers() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())
    result = service.ask(
        member=member,
        question_text="How much have we spent this month?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    turn = result.turns[0]
    assert turn.next_step_url == "/reports"


def test_next_step_link_is_absent_for_orders_quotations_answers() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())
    result = service.ask(
        member=member,
        question_text="What's the status of our purchase orders?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    turn = result.turns[0]
    assert turn.category.value == "orders_quotations"
    assert turn.next_step_url is None, (
        "FR-003A names no existing surface for orders_quotations — never invent one"
    )


# ---------------------------------------------------------------------------
# Phase 5 (T027, FR-008, US3): follow-up questions in context
# ---------------------------------------------------------------------------


def test_follow_up_turn_inherits_prior_context_and_appends_to_same_conversation() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    first = service.ask(
        member=member,
        question_text="How much have we spent this month?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )
    assert len(first.turns) == 1
    assert first.turns[0].category.value == "spend_savings"

    follow_up = service.ask(
        member=member,
        question_text="and last quarter?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
        conversation_id=first.id,
    )
    assert follow_up.id == first.id, "a follow-up must append to the same conversation"
    assert len(follow_up.turns) == 2
    assert follow_up.turns[1].category.value == "spend_savings", (
        "a follow-up with no keyword of its own must inherit the prior turn's category"
    )


def test_follow_up_with_new_subject_does_not_inherit_prior_category() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
            _seed_supplier_with_snapshot(
                cur,
                tenant_id,
                membership_id,
                supplier_name="Follow-up Subject Change Supplier",
                with_negotiation_brief=False,
            )
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    first = service.ask(
        member=member,
        question_text="How much have we spent this month?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )

    follow_up = service.ask(
        member=member,
        question_text="What's our supplier risk?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
        conversation_id=first.id,
    )
    assert follow_up.id == first.id
    assert follow_up.turns[1].category.value == "supplier_performance_risk", (
        "a follow-up naming its own subject must be treated as a fresh question, "
        "not inherit the prior turn's category"
    )


def test_continuation_of_another_tenants_conversation_raises_not_found() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_a_id, tenant_a_user, tenant_a_membership = _seed_workspace_with_spend(cur)
            tenant_b_id, tenant_b_user, tenant_b_membership = _seed_tenant(
                cur, email_suffix="other-tenant"
            )
        conn.commit()

    member_a = _member(tenant_a_id, tenant_a_user, tenant_a_membership)
    member_b = _member(tenant_b_id, tenant_b_user, tenant_b_membership)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    tenant_a_conversation = service.ask(
        member=member_a,
        question_text="How much have we spent this month?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )

    with pytest.raises(NotFoundError):
        service.ask(
            member=member_b,
            question_text="and last quarter?",
            idempotency_key=uuid4(),
            bearer_token="unused-in-this-path",
            conversation_id=tenant_a_conversation.id,
        )


def test_continuation_by_a_non_creator_member_raises_not_found() -> None:
    """FR-009 scopes read to creator (+ owner/buyer oversight), but continuing a
    conversation is a WRITE — only the original creator may append to their own
    conversation, even another owner in the same tenant may not."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, creator_user, creator_membership = _seed_workspace_with_spend(cur)
            other_user_id, other_membership_id = uuid4(), uuid4()
            other_email = "analyst-e2e-other-member@example.test"
            cur.execute(
                "insert into auth.users (id,email) values (%s,%s)",
                (other_user_id, other_email),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (other_membership_id, tenant_id, other_user_id, other_email),
            )
        conn.commit()

    creator = _member(tenant_id, creator_user, creator_membership)
    other_member = _member(tenant_id, other_user_id, other_membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    conversation = service.ask(
        member=creator,
        question_text="How much have we spent this month?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )

    with pytest.raises(NotFoundError):
        service.ask(
            member=other_member,
            question_text="and last quarter?",
            idempotency_key=uuid4(),
            bearer_token="unused-in-this-path",
            conversation_id=conversation.id,
        )


def test_continuation_of_a_nonexistent_conversation_raises_not_found() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    member = _member(tenant_id, user_id, membership_id)
    service = AnalystService(settings=get_settings(), intent_provider=FakeIntentProvider())

    with pytest.raises(NotFoundError):
        service.ask(
            member=member,
            question_text="and last quarter?",
            idempotency_key=uuid4(),
            bearer_token="unused-in-this-path",
            conversation_id=uuid4(),
        )

def test_conversation_list_scoping_by_member_and_role() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_1_id, member_1_id = _seed_workspace_with_spend(cur)
            user_2_id, member_2_id = _seed_additional_member(
                cur, tenant_id, role="viewer", email="analyst-e2e-viewer2@example.test"
            )
            user_3_id, member_3_id = _seed_additional_member(
                cur, tenant_id, role="owner", email="analyst-e2e-owner3@example.test"
            )
        conn.commit()

    service = get_analyst_service()
    mem_1 = _member(tenant_id, user_1_id, member_1_id, role=MemberRole.viewer)
    mem_2 = _member(
        tenant_id, user_2_id, member_2_id, role=MemberRole.viewer, email="viewer2@example.test"
    )
    mem_3 = _member(
        tenant_id, user_3_id, member_3_id, role=MemberRole.owner, email="owner3@example.test"
    )

    # member 1 asks two questions
    c1 = service.ask(
        member=mem_1,
        question_text="First question",
        idempotency_key=uuid4(),
        bearer_token="mock_token",
    )
    c2 = service.ask(
        member=mem_1,
        question_text="Second question",
        idempotency_key=uuid4(),
        bearer_token="mock_token",
    )

    # list for member 1
    l1 = service.list_conversations(member=mem_1)
    assert len(l1.items) == 2
    assert {c.id for c in l1.items} == {c1.id, c2.id}

    # list for member 2 (viewer)
    l2 = service.list_conversations(member=mem_2)
    assert len(l2.items) == 0

    # list for member 3 (owner)
    l3 = service.list_conversations(member=mem_3)
    assert len(l3.items) == 2
    assert {c.id for c in l3.items} == {c1.id, c2.id}


def test_get_conversation_replays_original_turn_unchanged() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_workspace_with_spend(cur)
        conn.commit()

    service = get_analyst_service()
    member = _member(tenant_id, user_id, membership_id, role=MemberRole.viewer)

    original = service.ask(
        member=member,
        question_text="What is my total spend?",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )

    reopened = service.get_conversation(member=member, conversation_id=original.id)
    assert reopened is not None
    assert len(reopened.turns) == len(original.turns)

    orig_turn = original.turns[0]
    reop_turn = reopened.turns[0]

    assert reop_turn.answer_text == orig_turn.answer_text
    assert reop_turn.calculation == orig_turn.calculation
    assert len(reop_turn.citations) == len(orig_turn.citations)
    if orig_turn.citations:
        assert reop_turn.citations[0].source_id == orig_turn.citations[0].source_id


def test_get_conversation_access_control() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            t1_id, u1_id, m1_id = _seed_workspace_with_spend(cur)
            t2_id, u2_id, m2_id = _seed_tenant(cur, email_suffix="t2")
            u3_id, m3_id = _seed_additional_member(
                cur, t1_id, role="viewer", email="analyst-e2e-viewer3@example.test"
            )
        conn.commit()

    service = get_analyst_service()
    mem1 = _member(t1_id, u1_id, m1_id, role=MemberRole.viewer)
    mem2 = _member(t2_id, u2_id, m2_id, role=MemberRole.viewer, email="t2@example.test")
    mem3 = _member(
        t1_id, u3_id, m3_id, role=MemberRole.viewer, email="viewer3@example.test"
    )

    c1 = service.ask(
        member=mem1,
        question_text="Hello",
        idempotency_key=uuid4(),
        bearer_token="unused-in-this-path",
    )

    # mem2 is another tenant
    assert service.get_conversation(member=mem2, conversation_id=c1.id) is None
    
    # mem3 is another member same tenant, but viewer role
    assert service.get_conversation(member=mem3, conversation_id=c1.id) is None
