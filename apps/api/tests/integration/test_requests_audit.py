"""Requests & approvals audit coverage — task T045 (008-requests-approvals, FR-013).

FR-013 requires every request submission, withdrawal, approval, rejection, and routing
escalation — plus threshold-rule and delegation management — to land in the append-only
`audit_event` log, the same way every other administrative action in this product already does.

Following test_organisation_audit.py's split for a concern that mixes a database guarantee with
application logic:

- That `audit_event` accepts, stores, and immutably retains a row for each of this chunk's
  action strings — proven directly by calling the `record_audit_event` SECURITY DEFINER
  function the exact way `AuditWriter.record` does (research.md R4), then confirming
  test_audit_append_only.py's immutability guarantee holds for these rows too.
- That `RequestsService`'s own methods actually call that writer with each of these action
  strings — `RequestsService` has no injectable audit seam (same as `OrganisationService`),
  so rather than a live HTTP round trip this is checked here by asserting each action string
  literally appears at a `get_audit_writer().record(...)` / `_record(...)` call site in
  `modules/requests/service.py`. The wire contract for the endpoints that trigger these is in
  tests/contract/test_approvals_contract.py and test_requests_contract.py.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the R2.1 migrations",
)

# Every action string modules/requests/service.py calls the audit writer with. The two decision
# actions come from f"requests.approval_step_{decision}" where decision is approved|rejected.
REQUESTS_AUDIT_ACTIONS: tuple[str, ...] = (
    "requests.purchase_request_created",
    "requests.purchase_request_updated",
    "requests.purchase_request_submitted",
    "requests.purchase_request_withdrawn",
    "requests.approval_step_approved",
    "requests.approval_step_rejected",
    "requests.approval_step_escalated",
    "requests.threshold_rule_created",
    "requests.threshold_rule_updated",
    "requests.threshold_rule_deleted",
    "requests.approval_delegation_created",
    "requests.approval_delegation_cancelled",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def make_tenant(cur: psycopg.Cursor, label: str) -> UUID:
    tenant_id, invitation_id = uuid4(), uuid4()
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
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"{label}@example.test", f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    return tenant_id


def act_as_owner(cur: psycopg.Cursor, tenant_id: UUID | str) -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (f'{{"tenant_id":"{tenant_id}","role":"authenticated","member_role":"owner"}}',),
    )


def record_via_rpc(
    cur: psycopg.Cursor, *, action: str, target: str = "{}"
) -> None:
    cur.execute(
        "select record_audit_event(%s, 'success', null, null, null, %s::jsonb, null)",
        (action, target),
    )


@pytest.mark.parametrize("action", REQUESTS_AUDIT_ACTIONS)
def test_audit_event_accepts_and_stores_every_requests_action(
    conn: psycopg.Connection, action: str
) -> None:
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "req-audit-accepts")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action, target='{"purchase_request_id": "test"}')
        cur.execute(
            "select action, outcome, target from audit_event "
            "where tenant_id = %s and action = %s",
            (tenant_id, action),
        )
        assert cur.fetchone() == (action, "success", {"purchase_request_id": "test"})


@pytest.mark.parametrize("action", REQUESTS_AUDIT_ACTIONS)
def test_requests_audit_events_are_immutable_like_every_other_action(
    conn: psycopg.Connection, action: str
) -> None:
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "req-audit-immutable")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update audit_event set outcome = 'refused' where tenant_id = %s",
                (tenant_id,),
            )
        conn.rollback()

        act_as_owner(cur, tenant_id)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "delete from audit_event where tenant_id = %s", (tenant_id,)
            )


def test_every_requests_action_is_distinct_and_searchable(
    conn: psycopg.Connection,
) -> None:
    assert len(REQUESTS_AUDIT_ACTIONS) == len(set(REQUESTS_AUDIT_ACTIONS))
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "req-audit-distinct")
        act_as_owner(cur, tenant_id)
        for action in REQUESTS_AUDIT_ACTIONS:
            record_via_rpc(cur, action=action)
        cur.execute(
            "select count(distinct action) from audit_event where tenant_id = %s",
            (tenant_id,),
        )
        assert cur.fetchone() == (len(REQUESTS_AUDIT_ACTIONS),)


def test_the_service_actually_emits_each_of_these_action_strings() -> None:
    """Closes the gap test_organisation_audit.py left to manual pre-commit verification: every
    action string above is literally present at an audit call site in the service source."""
    repo_root = Path(__file__).resolve().parents[4]
    source = (
        repo_root
        / "apps/api/src/procurepilot_api/modules/requests/service.py"
    ).read_text(encoding="utf-8")
    for action in REQUESTS_AUDIT_ACTIONS:
        if action in ("requests.approval_step_approved", "requests.approval_step_rejected"):
            # Emitted via f"requests.approval_step_{decision}".
            assert 'action=f"requests.approval_step_{decision}"' in source
        else:
            assert f'action="{action}"' in source, f"{action} not emitted by the service"
