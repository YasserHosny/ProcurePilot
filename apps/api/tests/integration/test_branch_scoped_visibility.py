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
    make_workspace_product,
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
    # T044: a submitted request + its approval step per branch.
    # request_a: branch A, requested by the unscoped manager (the scoped manager's branch-A
    #   scope is what would grant visibility).
    # request_b: branch B, requested by the SCOPED manager (exercises "the requester always
    #   sees their own request regardless of branch scope").
    # request_c: branch B, requested by the owner (the scoped manager is neither requester nor
    #   scoped to branch B — must resolve not-found, never forbidden).
    request_a: UUID
    request_b: UUID
    request_c: UUID
    step_a: UUID
    step_b: UUID
    # T044 (009-mobile-app-mvp): a low_stock_report per branch, same requester/branch shape as
    # request_a/b/c above, to prove low_stock_report's own scoped-visibility policy the same way.
    report_a: UUID
    report_b: UUID
    report_c: UUID
    # T033 (010-mobile-approvals-receipt): a delivery_quality_issue per request_a/b/c. Unlike
    # low_stock_report, delivery_quality_issue's own RLS derives visibility from the PARENT
    # request's requester/branch (an EXISTS join), not from who filed the issue itself — so these
    # three rows are attached directly to request_a/b/c rather than needing a fourth, separate
    # requester/branch shape of their own.
    issue_a: UUID
    issue_b: UUID
    issue_c: UUID


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

    product_id = make_workspace_product(cur, owner, name=f"{label}-product")
    # make_workspace_product acts as `owner` (via act_as) for its own inserts and does not
    # restore role afterward — reset back to the raw superuser context the rest of this
    # function's inserts rely on.
    cur.execute("reset role")

    def _request(branch_id: UUID, requester: Workspace) -> UUID:
        request_id = uuid4()
        cur.execute(
            "insert into purchase_request "
            "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status,"
            " submitted_at) "
            "values (%s,%s,%s,%s, current_date + interval '7 days', 'submitted', now())",
            (request_id, owner.tenant_id, branch_id, requester.membership_id),
        )
        return request_id

    def _step(request_id: UUID) -> UUID:
        step_id = uuid4()
        cur.execute(
            "insert into approval_step "
            "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
            "values (%s,%s,%s,%s,'owner_fallback','pending')",
            (step_id, owner.tenant_id, request_id, owner.membership_id),
        )
        return step_id

    def _report(branch_id: UUID, member: Workspace) -> UUID:
        report_id = uuid4()
        cur.execute(
            "insert into low_stock_report "
            "(id,tenant_id,branch_id,member_id,workspace_product_id) "
            "values (%s,%s,%s,%s,%s)",
            (report_id, owner.tenant_id, branch_id, member.membership_id, product_id),
        )
        return report_id

    def _quality_issue(request_id: UUID, reporter: Workspace) -> UUID:
        issue_id = uuid4()
        cur.execute(
            "insert into delivery_quality_issue "
            "(id,tenant_id,purchase_request_id,reported_by_membership_id,description) "
            "values (%s,%s,%s,%s,'Damaged in transit')",
            (issue_id, owner.tenant_id, request_id, reporter.membership_id),
        )
        return issue_id

    request_a = _request(branch_a, unscoped_manager)
    request_b = _request(branch_b, scoped_manager)
    request_c = _request(branch_b, owner)
    step_a = _step(request_a)
    step_b = _step(request_b)

    # Same shape as request_a/b/c: report_a exercises "sees their own branch", report_b exercises
    # "requester always sees their own report outside branch scope", report_c exercises "a direct
    # fetch of another branch's report resolves not-found, never forbidden".
    report_a = _report(branch_a, unscoped_manager)
    report_b = _report(branch_b, scoped_manager)
    report_c = _report(branch_b, owner)

    # delivery_quality_issue's own visibility rides request_a/b/c's requester/branch (see the
    # ScopedWorkspace field comment), not who filed the issue itself. issue_a/c are reported by
    # the owner to keep that distinction explicit; issue_b is reported by the scoped manager
    # (who is ALSO request_b's own requester) so it doubles as the literal "sees an issue they
    # personally reported" case without contradicting the real RLS mechanism.
    issue_a = _quality_issue(request_a, owner)
    issue_b = _quality_issue(request_b, scoped_manager)
    issue_c = _quality_issue(request_c, owner)

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
        request_a=request_a,
        request_b=request_b,
        request_c=request_c,
        step_a=step_a,
        step_b=step_b,
        report_a=report_a,
        report_b=report_b,
        report_c=report_c,
        issue_a=issue_a,
        issue_b=issue_b,
        issue_c=issue_c,
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


# ── T044: purchase_request and approval_step under the same visibility axis ──


def test_a_scoped_manager_sees_a_request_in_their_own_branch(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from purchase_request where branch_id = %s", (scoped.branch_a,))
        assert [row[0] for row in cur.fetchall()] == [scoped.request_a]


def test_a_scoped_manager_does_not_see_another_branchs_request(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        # request_c is in branch B, requested by the owner — outside both the manager's branch
        # scope and the requester-always clause.
        cur.execute("select count(*) from purchase_request where id = %s", (scoped.request_c,))
        assert cur.fetchone() == (0,)


def test_a_direct_fetch_of_another_branchs_request_resolves_not_found_not_forbidden(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select * from purchase_request where id = %s", (scoped.request_c,))
        assert cur.fetchone() is None  # empty result, never an error


def test_the_requester_sees_their_own_request_even_outside_their_branch_scope(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    # request_b is in branch B; the scoped manager is scoped to branch A only, but requested it.
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from purchase_request where id = %s", (scoped.request_b,))
        assert cur.fetchone() == (scoped.request_b,)


def test_an_unscoped_manager_sees_every_branchs_request(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.unscoped_manager)
        cur.execute("select count(*) from purchase_request")
        assert cur.fetchone() == (3,)


def test_removing_the_assignment_returns_the_manager_to_seeing_every_request(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select count(*) from purchase_request")
        assert cur.fetchone() == (2,)  # branch-A request + own branch-B request

        act_as(cur, scoped.owner)
        cur.execute(
            "delete from branch_role_assignment where id = %s", (scoped.assignment_id,)
        )

        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select count(*) from purchase_request")
        assert cur.fetchone() == (3,)


def test_approval_step_visibility_rides_the_parent_request_not_the_branch(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    # approval_step has no branch clause of its own: the scoped manager sees the step on the
    # request they submitted (request_b) but not the step on request_a, even though request_a
    # is in their assigned branch — they are neither its requester nor its assignee.
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from approval_step")
        assert [row[0] for row in cur.fetchall()] == [scoped.step_b]


def test_the_owner_sees_every_request_and_every_step(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        act_as(cur, scoped.owner)
        cur.execute("select count(*) from purchase_request")
        assert cur.fetchone() == (3,)
        cur.execute("select count(*) from approval_step")
        assert cur.fetchone() == (2,)


# ── T044 (009-mobile-app-mvp): low_stock_report under the same visibility axis ──


def test_a_scoped_manager_sees_a_low_stock_report_in_their_own_branch(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute(
            "select id from low_stock_report where branch_id = %s", (scoped.branch_a,)
        )
        assert [row[0] for row in cur.fetchall()] == [scoped.report_a]


def test_a_scoped_manager_does_not_see_another_branchs_low_stock_report(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        # report_c is in branch B, raised by the owner — outside both the manager's branch scope
        # and the "raised it themselves" clause.
        cur.execute(
            "select count(*) from low_stock_report where id = %s", (scoped.report_c,)
        )
        assert cur.fetchone() == (0,)


def test_a_direct_fetch_of_another_branchs_low_stock_report_resolves_not_found_not_forbidden(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select * from low_stock_report where id = %s", (scoped.report_c,))
        assert cur.fetchone() is None  # empty result, never an error


def test_the_requester_sees_their_own_low_stock_report_even_outside_their_branch_scope(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    # report_b is in branch B; the scoped manager is scoped to branch A only, but raised it.
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from low_stock_report where id = %s", (scoped.report_b,))
        assert cur.fetchone() == (scoped.report_b,)


# ── T033 (010-mobile-approvals-receipt): delivery_quality_issue under the same visibility axis ──
#
# Unlike low_stock_report, delivery_quality_issue's own RLS derives visibility from the PARENT
# purchase_request's requester/branch (an EXISTS join to purchase_request), not from the issue's
# own reported_by_membership_id — see delivery_quality_issue_scoped_visibility,
# 20260913000003_delivery_quality_issue.sql. issue_a/b/c are attached to request_a/b/c
# respectively, so they inherit the exact same three-case shape already proven for
# purchase_request itself above.


def test_a_scoped_manager_sees_a_quality_issue_on_their_own_branchs_request(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute(
            "select id from delivery_quality_issue where purchase_request_id = %s",
            (scoped.request_a,),
        )
        assert [row[0] for row in cur.fetchall()] == [scoped.issue_a]


def test_a_scoped_manager_does_not_see_another_branchs_quality_issue(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        # issue_c is on request_c (branch B, requested by the owner) — outside both the
        # manager's branch scope and the parent request's own requester clause.
        cur.execute(
            "select count(*) from delivery_quality_issue where id = %s", (scoped.issue_c,)
        )
        assert cur.fetchone() == (0,)


def test_a_direct_fetch_of_another_branchs_quality_issue_resolves_not_found_not_forbidden(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select * from delivery_quality_issue where id = %s", (scoped.issue_c,))
        assert cur.fetchone() is None  # empty result, never an error


def test_the_requester_sees_a_quality_issue_on_their_own_request_even_outside_branch_scope(
    conn: psycopg.Connection, scoped: ScopedWorkspace
) -> None:
    # issue_b is on request_b (branch B, requested by the scoped manager); the scoped manager
    # is scoped to branch A only, but visibility rides request_b's own requester, not the
    # manager's branch scope.
    with conn.cursor() as cur:
        _act_as_scoped(cur, scoped.scoped_manager)
        cur.execute("select id from delivery_quality_issue where id = %s", (scoped.issue_b,))
        assert cur.fetchone() == (scoped.issue_b,)
