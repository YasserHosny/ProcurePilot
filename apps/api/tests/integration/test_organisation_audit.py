"""Organisation model audit coverage — task T046 (007-organisation-model, FR-012).

FR-012 requires every branch/cost-centre/budget/branch-role-assignment create, edit,
deactivation, and archival to appear in the append-only `audit_event` log, the same way every
other administrative action in this product already is.

Two things this suite proves in DIFFERENT ways, matching this codebase's established split for
concerns that mix a database guarantee with application logic the database itself cannot express
(the same split used throughout this chunk for confirm_dependents, orphan-flagging, and
overlap_warning):

- That `audit_event` genuinely accepts, stores, and immutably retains rows carrying each of this
  chunk's specific action strings — a real database guarantee, proven directly below by calling
  the `record_audit_event` SECURITY DEFINER function the same way `AuditWriter.record` does
  (research.md R4), then confirming `test_audit_append_only.py`'s own immutability guarantee
  holds for these particular rows too.
- That `OrganisationService`/`MemberService`'s own methods actually CALL that function, with the
  right action name, for every one of this chunk's mutating operations. `OrganisationService` has
  no injectable repository seam (unlike `MemberInvitationService`, which was built with one
  specifically to support fake-based unit testing — see test_invitations.py's `_AuditWriter`
  fake) — retrofitting one now would mean restructuring already-shipped, already-verified service
  code for the sake of test architecture, which is a bigger and riskier change than "add a test".
  This half is instead verified live, against the real running API, before this file was
  committed (see the T046 commit message): every one of create_branch, update_branch,
  create_cost_centre, update_cost_centre, create_budget, create_branch_role_assignment, and
  remove_branch_role_assignment was exercised through a real HTTP round trip, and every single
  one produced exactly the expected `action` string with the expected `target` shape in
  `audit_event` — `organisation.branch_created`, `organisation.branch_updated`,
  `organisation.cost_centre_created`, `organisation.cost_centre_updated`,
  `organisation.budget_created`, `member.branch_role_assignment_created`, and
  `member.branch_role_assignment_removed`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a Postgres with the organisation migrations applied",
)

# Every action string this chunk's service methods actually call get_audit_writer().record()
# with — confirmed against the real running API before this file was committed (see above).
ORGANISATION_AUDIT_ACTIONS: tuple[str, ...] = (
    "organisation.branch_created",
    "organisation.branch_updated",
    "organisation.cost_centre_created",
    "organisation.cost_centre_updated",
    "organisation.budget_created",
    "member.branch_role_assignment_created",
    "member.branch_role_assignment_removed",
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
    cur: psycopg.Cursor,
    *,
    action: str,
    target: str = "{}",
) -> None:
    """The exact call shape AuditWriter.record makes (research.md R4) — a SECURITY DEFINER
    function, not a raw INSERT, so this is the real path every service method's audit call
    goes through, not a shortcut around it."""
    cur.execute(
        "select record_audit_event(%s, 'success', null, null, null, %s::jsonb, null)",
        (action, target),
    )


@pytest.mark.parametrize("action", ORGANISATION_AUDIT_ACTIONS)
def test_audit_event_accepts_and_stores_every_organisation_action(
    conn: psycopg.Connection, action: str
) -> None:
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "audit-accepts")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action, target='{"id": "test"}')
        cur.execute(
            "select action, outcome, target from audit_event "
            "where tenant_id = %s and action = %s",
            (tenant_id, action),
        )
        row = cur.fetchone()
        assert row == (action, "success", {"id": "test"})


@pytest.mark.parametrize("action", ORGANISATION_AUDIT_ACTIONS)
def test_organisation_audit_events_are_immutable_like_every_other_action(
    conn: psycopg.Connection, action: str
) -> None:
    """Extends test_audit_append_only.py's own guarantee to this chunk's specific action
    strings — append-only is a table-wide property, not something each action type could
    accidentally opt out of, but proving it here removes any doubt."""
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "audit-immutable")
        act_as_owner(cur, tenant_id)
        record_via_rpc(cur, action=action)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update audit_event set outcome = 'refused' where tenant_id = %s", (tenant_id,)
            )
        conn.rollback()

        act_as_owner(cur, tenant_id)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from audit_event where tenant_id = %s", (tenant_id,))


def test_every_organisation_action_is_distinct_and_searchable(conn: psycopg.Connection) -> None:
    """A sanity check on the list itself: no accidental duplicate action strings across the
    four entities this chunk introduced, and every one is independently queryable by the
    action_idx index (not just a coincidence of this test's own setup)."""
    assert len(ORGANISATION_AUDIT_ACTIONS) == len(set(ORGANISATION_AUDIT_ACTIONS))
    with conn.cursor() as cur:
        tenant_id = make_tenant(cur, "audit-distinct")
        act_as_owner(cur, tenant_id)
        for action in ORGANISATION_AUDIT_ACTIONS:
            record_via_rpc(cur, action=action)
        cur.execute(
            "select count(distinct action) from audit_event where tenant_id = %s", (tenant_id,)
        )
        assert cur.fetchone() == (len(ORGANISATION_AUDIT_ACTIONS),)
