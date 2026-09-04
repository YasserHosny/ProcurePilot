"""Budget definitions — task T029 (007-organisation-model, User Story 3).

FR-005's overlap-warning FLAG itself is application logic (OrganisationService.create_budget
computes it by fetching existing budgets for the same scope/target and comparing computed date
ranges) — there is no DB constraint that could express "warn but don't block." This suite proves
the two facts that logic depends on: the database never blocks an overlapping insert (no unique
constraint on scope+period), and the `budget_scope_target` check constraint is real and rejects
a mismatched scope/reference pairing. The full overlap-detection algorithm and its warning flag
get their proof from OrganisationService's own tests and from the E2E suite (T031), matching the
established pattern for FR-009 (confirm_dependents) and FR-010 (orphan-flagging) in this chunk.
"""

from __future__ import annotations

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
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a Postgres with the organisation migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def make_branch(cur: psycopg.Cursor, workspace: Workspace, *, name: str = "Branch") -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, name),
    )
    return branch_id


def make_organisation_budget(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    amount: str = "1000",
    currency: str = "GBP",
    period: str = "monthly",
    period_start: str = "2026-08-01",
) -> UUID:
    budget_id = uuid4()
    cur.execute(
        "insert into budget "
        "(id,tenant_id,amount,currency,period,period_start,scope,created_by) "
        "values (%s,%s,%s,%s,%s,%s,'organisation',%s)",
        (
            budget_id,
            workspace.tenant_id,
            amount,
            currency,
            period,
            period_start,
            workspace.membership_id,
        ),
    )
    return budget_id


def test_an_organisation_wide_budget_is_visible_to_its_own_workspace(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-org-wide")
        act_as(cur, workspace)
        budget_id = make_organisation_budget(cur, workspace, amount="5000", currency="GBP")
        cur.execute(
            "select amount, currency, scope, branch_id, cost_centre_id "
            "from budget where id = %s",
            (budget_id,),
        )
        assert cur.fetchone() == (5000, "GBP", "organisation", None, None)


def test_budget_currency_is_never_inferred_from_tenant_currency(conn: object) -> None:
    """research.md R3: a budget MAY be defined in a currency other than the tenant's own —
    the column is independently set, never derived."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-explicit-currency")
        act_as(cur, workspace)
        assert workspace.role == "owner"
        # The workspace itself is GBP (see catalogue_helpers.make_workspace); the budget below
        # deliberately uses a different, real supported currency to prove no inference happens.
        budget_id = make_organisation_budget(cur, workspace, amount="100", currency="USD")
        cur.execute("select currency from budget where id = %s", (budget_id,))
        assert cur.fetchone() == ("USD",)


def test_a_branch_scoped_budget_requires_a_branch_id(conn: object) -> None:
    """The budget_scope_target check constraint — a real database guarantee, not just
    application validation."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-scope-branch-missing")
        act_as(cur, workspace)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into budget "
                "(id,tenant_id,amount,currency,period,period_start,scope,created_by) "
                "values (%s,%s,1000,'GBP','monthly','2026-08-01','branch',%s)",
                (uuid4(), workspace.tenant_id, workspace.membership_id),
            )


def test_a_cost_centre_scoped_budget_cannot_also_carry_a_branch_id(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-scope-mixed")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cost_centre_id = uuid4()
        cur.execute(
            "insert into cost_centre (id,tenant_id,name,code) values (%s,%s,'Kitchen','KIT-01')",
            (cost_centre_id, workspace.tenant_id),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into budget "
                "(id,tenant_id,amount,currency,period,period_start,scope,branch_id,"
                "cost_centre_id,created_by) "
                "values (%s,%s,1000,'GBP','monthly','2026-08-01','cost_centre',%s,%s,%s)",
                (
                    uuid4(),
                    workspace.tenant_id,
                    branch_id,
                    cost_centre_id,
                    workspace.membership_id,
                ),
            )


def test_an_organisation_scoped_budget_cannot_carry_a_branch_or_cost_centre_id(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-scope-org-with-branch")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into budget "
                "(id,tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "
                "values (%s,%s,1000,'GBP','monthly','2026-08-01','organisation',%s,%s)",
                (uuid4(), workspace.tenant_id, branch_id, workspace.membership_id),
            )


def test_overlapping_periods_for_the_same_scope_are_not_blocked_at_the_database_level(
    conn: object,
) -> None:
    """FR-005, Acceptance Scenario 3: the database must never refuse this — the overlap is
    surfaced as a warning by application logic, not prevented here."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-overlap-allowed")
        act_as(cur, workspace)
        make_organisation_budget(
            cur, workspace, amount="10000", period="annual", period_start="2026-01-01"
        )
        # A supplementary quarterly top-up overlapping the running annual budget — must succeed.
        second_id = make_organisation_budget(
            cur, workspace, amount="2000", period="quarterly", period_start="2026-04-01"
        )
        cur.execute("select count(*) from budget where id = %s", (second_id,))
        assert cur.fetchone() == (1,)
        cur.execute("select count(*) from budget where tenant_id = %s", (workspace.tenant_id,))
        assert cur.fetchone() == (2,)


def test_budgets_for_the_same_scope_are_queryable_for_overlap_computation(conn: object) -> None:
    """The exact data OrganisationService's overlap check reads: every existing budget's period
    and period_start for a given scope (+ branch/cost-centre target)."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "budget-overlap-query")
        act_as(cur, workspace)
        make_organisation_budget(cur, workspace, period="monthly", period_start="2026-08-01")
        make_organisation_budget(cur, workspace, period="monthly", period_start="2026-09-01")
        cur.execute(
            "select period, period_start from budget "
            "where tenant_id = %s and scope = 'organisation' order by period_start",
            (workspace.tenant_id,),
        )
        rows = cur.fetchall()
        assert [r[0] for r in rows] == ["monthly", "monthly"]


# --- owner-only write access (matches test_cost_centres.py's direct require_role() style) ---

WRITE_ROLES = (MemberRole.owner,)
ALL_ROLES = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)
BUDGET_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "create-budget": WRITE_ROLES,
    "read-budgets": ALL_ROLES,
}


def member_with_role(role: MemberRole) -> object:
    from procurepilot_api.deps import CurrentMember

    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="member@example.test",
        role=role,
    )


@pytest.mark.parametrize("role", ALL_ROLES, ids=[r.value for r in ALL_ROLES])
@pytest.mark.parametrize("guard", sorted(BUDGET_GUARDS), ids=sorted(BUDGET_GUARDS))
def test_budget_role_matrix_holds_in_both_directions(guard: str, role: MemberRole) -> None:
    dependency = require_role(*BUDGET_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in BUDGET_GUARDS[guard]
    if permitted:
        assert dependency(member) == member, f"{role.value} should be permitted to {guard}"
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)
