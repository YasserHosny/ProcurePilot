"""Real (non-mocked) end-to-end test for AnalystService.ask() (R4.2, T013).

Written during orchestrator review of the Phase 3 dispatch: the dispatch's own
integration test (test_analyst_api.py) mocks AnalystService entirely via a FastAPI
dependency override, so it never once exercised service.py's actual SQL against a
real database. This test does — it proves the full round trip (conversation +
turn + citation + audit event, atomically, against real RLS) actually works,
not just that the HTTP layer wires a mock correctly.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.analyst.intent import FakeIntentProvider
from procurepilot_api.modules.analyst.service import AnalystService
from procurepilot_api.modules.auth.jwt import MemberRole

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _seed_workspace_with_spend(cur: psycopg.Cursor) -> tuple[UUID, UUID, UUID]:
    """One tenant, one owner member, one purchase order — enough to ground a
    spend_savings question with a real citation."""
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    supplier_id, order_id = uuid4(), uuid4()

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
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, "analyst-e2e@example.test"),
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, "analyst-e2e@example.test", f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, "Analyst E2E Ltd", f"analyst-e2e-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, "analyst-e2e@example.test"),
    )
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


def _member(tenant_id: UUID, user_id: UUID, membership_id: UUID) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email="analyst-e2e@example.test",
        role=MemberRole.owner,
    )


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
