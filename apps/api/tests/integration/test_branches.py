"""Branch CRUD — task T015 (007-organisation-model, User Story 1).

Two things this suite deliberately does NOT prove, and why:

- The actual HTTP-level `confirm_dependents` 422 refusal (FR-009's "explicit confirmation
  naming what is still attached") is application logic in `OrganisationService`, not a database
  guarantee — there is no trigger that could express it. This suite proves the two facts that
  logic depends on (dependents are queryable by branch_id, and the database itself never blocks
  a deactivation with dependents attached), matching this codebase's own established precedent
  in test_suppliers.py's `test_deleting_a_referenced_supplier_nulls_the_preference_at_database_
  level`, which carries the identical caveat for the analogous supplier-archive 409 path. The
  full request/response proof is `apps/web/tests/e2e/organisation-branches.spec.ts` (T017),
  which runs against the real, live API.
- No-hard-delete (FR-009) is proven structurally below: no DELETE route for a branch is
  registered on the app at all, so there is no path to hit even if a client tried.
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
from procurepilot_api.main import API_PREFIX, create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a Postgres with the organisation migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def make_branch(cur: psycopg.Cursor, workspace: Workspace, *, name: str = "Main Branch") -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, name),
    )
    return branch_id


def test_a_created_branch_is_visible_to_its_own_workspace(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "branch-create")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace, name="Riyadh Warehouse")
        cur.execute("select name, is_active from branch where id = %s", (branch_id,))
        assert cur.fetchone() == ("Riyadh Warehouse", True)


def test_deactivating_a_branch_with_dependents_is_not_blocked_at_the_database_level(
    conn: object,
) -> None:
    """Acceptance Scenario 3: 'the system allows the deactivation... but requires an explicit
    confirmation' — the ALLOWING half is a database guarantee (nothing here may block it); the
    CONFIRMATION half is application logic proven end-to-end by the E2E suite, not here."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "branch-deactivate-with-dependents")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cost_centre_id = uuid4()
        cur.execute(
            "insert into cost_centre (id,tenant_id,name,code,branch_id) "
            "values (%s,%s,'Kitchen','KIT-01',%s)",
            (cost_centre_id, workspace.tenant_id, branch_id),
        )
        cur.execute(
            "update branch set is_active = false where id = %s returning is_active",
            (branch_id,),
        )
        assert cur.fetchone() == (False,)
        # The dependent survives untouched — deactivation is not a cascade.
        cur.execute("select branch_id from cost_centre where id = %s", (cost_centre_id,))
        assert cur.fetchone() == (branch_id,)


def test_a_branchs_dependents_are_queryable_by_branch_id(conn: object) -> None:
    """The exact data OrganisationService's confirm_dependents check reads: cost centres AND
    branch role assignments linked to this branch, each independently."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "branch-dependents-query")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cost_centre_id = uuid4()
        cur.execute(
            "insert into cost_centre (id,tenant_id,name,code,branch_id) "
            "values (%s,%s,'Facilities','FAC-01',%s)",
            (cost_centre_id, workspace.tenant_id, branch_id),
        )
        assignment_id = uuid4()
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (assignment_id, workspace.tenant_id, workspace.membership_id, branch_id),
        )
        cur.execute(
            "select count(*) from cost_centre where branch_id = %s", (branch_id,)
        )
        assert cur.fetchone() == (1,)
        cur.execute(
            "select count(*) from branch_role_assignment where branch_id = %s", (branch_id,)
        )
        assert cur.fetchone() == (1,)


def test_a_branch_with_no_dependents_reports_none(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "branch-no-dependents")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cur.execute("select count(*) from cost_centre where branch_id = %s", (branch_id,))
        assert cur.fetchone() == (0,)
        cur.execute(
            "select count(*) from branch_role_assignment where branch_id = %s", (branch_id,)
        )
        assert cur.fetchone() == (0,)


def test_no_hard_delete_route_exists_for_branches() -> None:
    """FR-009: deactivation is the only retirement path — there must be no DELETE endpoint to
    even attempt a hard delete through."""
    app = create_app()
    branch_paths = {
        route.path: route.methods
        for route in app.routes
        if str(route.path).startswith(f"{API_PREFIX}/organisation/branches")
    }
    for methods in branch_paths.values():
        assert "DELETE" not in methods


# --- owner-only write access (matches test_catalogue_rbac.py's direct require_role() style) --

WRITE_ROLES = (MemberRole.owner,)
ALL_ROLES = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)
BRANCH_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "create-branch": WRITE_ROLES,
    "update-branch": WRITE_ROLES,
    "read-branches": ALL_ROLES,
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
@pytest.mark.parametrize("guard", sorted(BRANCH_GUARDS), ids=sorted(BRANCH_GUARDS))
def test_branch_role_matrix_holds_in_both_directions(guard: str, role: MemberRole) -> None:
    dependency = require_role(*BRANCH_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in BRANCH_GUARDS[guard]
    if permitted:
        assert dependency(member) == member, f"{role.value} should be permitted to {guard}"
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)
