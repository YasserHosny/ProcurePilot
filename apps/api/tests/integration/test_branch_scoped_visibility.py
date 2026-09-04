"""Branch-scoped visibility — task T036 (007-organisation-model, User Story 4).

THE test this user story exists to make possible: proves the within-tenant visibility axis
(research.md R1) that branch/cost_centre/budget's own RESTRICTIVE RLS policies were built for
back in Setup (migrations 20260822000037-40) — this file is the proof, not the mechanism itself,
matching this repo's own convention (chunk 4.1's test_tenant_isolation.py is the analogous proof
for cross-tenant isolation).

One workspace, four members:
- The owner (from make_workspace) — sees everything in the tenant, always.
- A SCOPED branch_manager, assigned to Branch A only — sees Branch A and everything linked to
  it, never Branch B or anything linked to Branch B.
- An UNSCOPED branch_manager — holds a branch-scopable role but has no branch_role_assignment
  row at all — sees everything, same as owner (research.md R1's fallback for "not yet assigned").
- The scoped manager's assignment is later removed entirely, proving they fall back to the same
  unscoped (tenant-wide) visibility once nothing scopes them anymore.

Two branches, each with one linked cost centre and one linked (branch-scoped) budget, so the same
three tables' RESTRICTIVE policies are all exercised together, not just branch's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a Postgres with the organisation migrations applied",
)


@dataclass(frozen=True)
class ScopedWorkspace:
    owner: Workspace
    scoped_manager: Workspace
    unscoped_manager: Workspace
    branch_a: UUID
    branch_b: UUID
    cost_centre_a: UUID
    cost_centre_b: UUID
    budget_a: UUID
    budget_b: UUID
    assignment_id: UUID


def _make_member(
    cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str
) -> Workspace:
    """A second (or third) membership in an ALREADY-CREATED tenant — elevated-role inserts,
    same as make_workspace's own rows, must happen before any act_as call."""
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}@example.test"),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def make_scoped_workspace(cur: psycopg.Cursor, label: str) -> ScopedWorkspace:
    owner = make_workspace(cur, label)
    scoped_manager = _make_member(cur, owner.tenant_id, f"{label}-scoped", "branch_manager")
    unscoped_manager = _make_member(cur, owner.tenant_id, f"{label}-unscoped", "branch_manager")

    branch_a, branch_b = uuid4(), uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Branch A','GB')",
        (branch_a, owner.tenant_id),
    )
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Branch B','GB')",
        (branch_b, owner.tenant_id),
    )

    cost_centre_a, cost_centre_b = uuid4(), uuid4()
    cur.execute(
        "insert into cost_centre (id,tenant_id,name,code,branch_id) "
        "values (%s,%s,'CC A','CC-A',%s)",
        (cost_centre_a, owner.tenant_id, branch_a),
    )
    cur.execute(
        "insert into cost_centre (id,tenant_id,name,code,branch_id) "
        "values (%s,%s,'CC B','CC-B',%s)",
        (cost_centre_b, owner.tenant_id, branch_b),
    )

    budget_a, budget_b = uuid4(), uuid4()
    cur.execute(
        "insert into budget "
        "(id,tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "
        "values (%s,%s,1000,'GBP','monthly','2026-08-01','branch',%s,%s)",
        (budget_a, owner.tenant_id, branch_a, owner.membership_id),
    )
    cur.execute(
        "insert into budget "
        "(id,tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "
        "values (%s,%s,1000,'GBP','monthly','2026-08-01','branch',%s,%s)",
        (budget_b, owner.tenant_id, branch_b, owner.membership_id),
    )

    assignment_id = uuid4()
    cur.execute(
        "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
        "values (%s,%s,%s,%s)",
        (assignment_id, owner.tenant_id, scoped_manager.membership_id, branch_a),
    )

    return ScopedWorkspace(
        owner=owner,
        scoped_manager=scoped_manager,
        unscoped_manager=unscoped_manager,
        branch_a=branch_a,
        branch_b=branch_b,
        cost_centre_a=cost_centre_a,
        cost_centre_b=cost_centre_b,
        budget_a=budget_a,
        budget_b=budget_b,
        assignment_id=assignment_id,
    )


@pytest.fixture
def scoped(conn: psycopg.Connection) -> ScopedWorkspace:
    with conn.cursor() as cur:
        return make_scoped_workspace(cur, "bsv")


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


def _act_as_scoped(cur: psycopg.Cursor, workspace: Workspace) -> None:
    """Same shape as catalogue_helpers.act_as, but sets member_role from the workspace's own
    role rather than assuming 'owner' — branch_manager here, not owner."""
    cur.execute("set local role authenticated")
    claims = (
        f'{{"sub":"{workspace.user_id}","tenant_id":"{workspace.tenant_id}",'
        f'"role":"authenticated","member_role":"{workspace.role}"}}'
    )
    cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))


def test_the_owner_sees_both_branches_and_everything_linked_to_them(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        act_as(cur, scoped.owner)
        cur.execute("select count(*) from branch where tenant_id = %s", (scoped.owner.tenant_id,))
        assert cur.fetchone() == (2,)
        cur.execute(
            "select count(*) from cost_centre where tenant_id = %s", (scoped.owner.tenant_id,)
        )
        assert cur.fetchone() == (2,)
        cur.execute("select count(*) from budget where tenant_id = %s", (scoped.owner.tenant_id,))
        assert cur.fetchone() == (2,)


def test_a_scoped_manager_sees_only_their_own_branch(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from branch order by name")
        assert [row[0] for row in cur.fetchall()] == [scoped.branch_a]


def test_a_scoped_manager_sees_only_their_own_cost_centre(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from cost_centre")
        assert [row[0] for row in cur.fetchall()] == [scoped.cost_centre_a]


def test_a_scoped_manager_sees_only_their_own_branchs_budget(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from budget")
        assert [row[0] for row in cur.fetchall()] == [scoped.budget_a]


def test_a_direct_request_for_the_other_branch_resolves_not_found(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    """FR-008: same-tenant, different-branch must look exactly like the resource does not
    exist — never an explicit permission-denied signal."""
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from branch where id = %s", (scoped.branch_b,))
        assert cur.fetchall() == []
        cur.execute("select count(*) from branch where id = %s", (scoped.branch_b,))
        assert cur.fetchone() == (0,)


def test_a_direct_request_for_the_other_branchs_cost_centre_resolves_not_found(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from cost_centre where id = %s", (scoped.cost_centre_b,))
        assert cur.fetchall() == []


def test_a_direct_request_for_the_other_branchs_budget_resolves_not_found(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from budget where id = %s", (scoped.budget_b,))
        assert cur.fetchall() == []


def test_an_unassigned_branch_scopable_member_sees_everything(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    """research.md R1: a branch-scopable role with no assignment yet falls back to unscoped
    (tenant-wide) visibility, same as owner — never zero visibility."""
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.unscoped_manager)
        cur.execute("select count(*) from branch")
        assert cur.fetchone() == (2,)
        cur.execute("select count(*) from cost_centre")
        assert cur.fetchone() == (2,)
        cur.execute("select count(*) from budget")
        assert cur.fetchone() == (2,)


def test_removing_the_last_assignment_returns_the_member_to_unscoped_visibility(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        # Confirm scoped first, so the removal's effect is actually visible in this same test.
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select count(*) from branch")
        assert cur.fetchone() == (1,)

        # Remove as owner (the delete itself needs a role that can write this table).
        act_as(cur, scoped.owner)
        cur.execute(
            "delete from branch_role_assignment where id = %s", (scoped.assignment_id,)
        )
        assert cur.rowcount == 1

        # The same member, now with zero assignments, is unscoped — sees both branches.
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select count(*) from branch")
        assert cur.fetchone() == (2,)
        cur.execute("select count(*) from cost_centre")
        assert cur.fetchone() == (2,)
        cur.execute("select count(*) from budget")
        assert cur.fetchone() == (2,)


def test_a_scoped_managers_own_branch_role_assignment_row_is_visible_to_them(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    """branch_role_assignment's own RESTRICTIVE policy: an owner sees every assignment; a
    non-owner sees only their own row(s)."""
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select membership_id from branch_role_assignment")
        assert [row[0] for row in cur.fetchall()] == [scoped.scoped_manager.membership_id]


def test_an_unassigned_managers_visibility_of_assignments_is_empty_not_an_error(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.unscoped_manager)
        cur.execute("select count(*) from branch_role_assignment")
        assert cur.fetchone() == (0,)
