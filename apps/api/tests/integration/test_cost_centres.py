"""Cost centre CRUD — task T022 (007-organisation-model, User Story 2).

FR-003 (duplicate code rejection) is a real database guarantee (the `cost_centre_tenant_
code_key` unique constraint) and is proven directly here. FR-010 (orphan-flagging when a linked
branch is deactivated or the budget owner is removed) is application logic layered on top of
facts this suite proves ARE queryable (branch.is_active, membership.status) — the actual
flagging behaviour and the API's computed `orphan_reason` field get their full proof from the
E2E suite (T024) and from OrganisationService's own unit-level correctness, matching this
codebase's established precedent (test_suppliers.py, test_branches.py) for APIs that combine a
database guarantee with application logic the database itself cannot express.
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


def make_cost_centre(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    name: str = "Cost Centre",
    code: str,
    branch_id: UUID | None = None,
    budget_owner_membership_id: UUID | None = None,
) -> UUID:
    cost_centre_id = uuid4()
    cur.execute(
        "insert into cost_centre (id,tenant_id,name,code,branch_id,budget_owner_membership_id) "
        "values (%s,%s,%s,%s,%s,%s)",
        (cost_centre_id, workspace.tenant_id, name, code, branch_id, budget_owner_membership_id),
    )
    return cost_centre_id


def test_a_created_cost_centre_is_visible_to_its_own_workspace(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-create")
        act_as(cur, workspace)
        cc_id = make_cost_centre(cur, workspace, name="Kitchen", code="KIT-01")
        cur.execute(
            "select name, code, is_orphaned, is_archived from cost_centre where id = %s",
            (cc_id,),
        )
        assert cur.fetchone() == ("Kitchen", "KIT-01", False, False)


def test_an_organisation_wide_cost_centre_has_no_branch(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-org-wide")
        act_as(cur, workspace)
        cc_id = make_cost_centre(cur, workspace, code="GEN-01")
        cur.execute("select branch_id from cost_centre where id = %s", (cc_id,))
        assert cur.fetchone() == (None,)


def test_duplicate_code_within_the_same_tenant_is_rejected(conn: object) -> None:
    """FR-003: a real unique constraint, not application-layer validation alone."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-duplicate")
        act_as(cur, workspace)
        make_cost_centre(cur, workspace, name="Kitchen", code="DUP-01")
        with pytest.raises(psycopg.errors.UniqueViolation):
            make_cost_centre(cur, workspace, name="Second Kitchen", code="DUP-01")


def test_the_same_code_is_allowed_across_different_tenants(conn: object) -> None:
    """The uniqueness is per-tenant, not global — confirms the constraint is
    `unique(tenant_id, code)`, not `unique(code)`."""
    with conn.cursor() as cur:
        # Both workspaces first, while still the elevated role make_workspace needs —
        # act_as switches to `authenticated`, which cannot insert tenant/membership rows.
        alpha = make_workspace(cur, "cc-tenant-alpha")
        beta = make_workspace(cur, "cc-tenant-beta")

        act_as(cur, alpha)
        make_cost_centre(cur, alpha, code="SHARED-01")

        act_as(cur, beta)
        # Must not raise — a different tenant may reuse the same code.
        make_cost_centre(cur, beta, code="SHARED-01")
        cur.execute("select count(*) from cost_centre where code = 'SHARED-01'")
        assert cur.fetchone() == (1,)  # RLS: beta only ever sees its own row


def test_orphan_flag_is_a_real_settable_column(conn: object) -> None:
    """The flag itself (FR-010) — the application logic that decides WHEN to set it lives in
    OrganisationService/MemberService, proven end-to-end by the E2E suite; this proves the
    column the flag lives in behaves as a real, queryable boolean."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-orphan-flag")
        act_as(cur, workspace)
        cc_id = make_cost_centre(cur, workspace, code="ORPH-01")
        cur.execute(
            "update cost_centre set is_orphaned = true where id = %s returning is_orphaned",
            (cc_id,),
        )
        assert cur.fetchone() == (True,)


def test_a_cost_centres_branch_deactivation_state_is_queryable(conn: object) -> None:
    """The exact fact OrganisationService's orphan-flagging-on-deactivation logic reads: a
    linked cost centre's branch's own is_active column."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-branch-state")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cc_id = make_cost_centre(cur, workspace, code="BRN-01", branch_id=branch_id)
        cur.execute("update branch set is_active = false where id = %s", (branch_id,))
        cur.execute(
            "select b.is_active from cost_centre cc "
            "join branch b on b.id = cc.branch_id where cc.id = %s",
            (cc_id,),
        )
        assert cur.fetchone() == (False,)


def test_a_cost_centres_budget_owners_removal_state_is_queryable(conn: object) -> None:
    """The exact fact OrganisationService's orphan-flagging-on-member-removal logic reads: the
    budget owner's own membership.status column. Member removal is a soft delete (status set to
    'removed', not a row DELETE — see MemberService.remove_member), so this join must still
    resolve after "removal", not silently vanish via the FK."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "cc-owner-removed")

        # Still the elevated role: a second membership row needs auth.users + membership
        # inserts, both privileged, same as make_workspace's own rows above.
        budget_owner_id, budget_owner_user_id = uuid4(), uuid4()
        cur.execute(
            "insert into auth.users (id,email) values (%s,%s)",
            (budget_owner_user_id, "budget-owner@example.test"),
        )
        cur.execute(
            "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
            "values (%s,%s,%s,%s,'buyer',false)",
            (
                budget_owner_id,
                workspace.tenant_id,
                budget_owner_user_id,
                "budget-owner@example.test",
            ),
        )

        act_as(cur, workspace)
        cc_id = make_cost_centre(
            cur,
            workspace,
            code="OWN-01",
            budget_owner_membership_id=budget_owner_id,
        )
        cur.execute(
            "update membership set status = 'removed', is_active_workspace = false "
            "where id = %s",
            (budget_owner_id,),
        )
        cur.execute(
            "select m.status from cost_centre cc "
            "join membership m on m.id = cc.budget_owner_membership_id where cc.id = %s",
            (cc_id,),
        )
        assert cur.fetchone() == ("removed",)


# --- owner-only write access (matches test_branches.py's direct require_role() style) -------

WRITE_ROLES = (MemberRole.owner,)
ALL_ROLES = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)
COST_CENTRE_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "create-cost-centre": WRITE_ROLES,
    "update-cost-centre": WRITE_ROLES,
    "read-cost-centres": ALL_ROLES,
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
@pytest.mark.parametrize("guard", sorted(COST_CENTRE_GUARDS), ids=sorted(COST_CENTRE_GUARDS))
def test_cost_centre_role_matrix_holds_in_both_directions(guard: str, role: MemberRole) -> None:
    dependency = require_role(*COST_CENTRE_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in COST_CENTRE_GUARDS[guard]
    if permitted:
        assert dependency(member) == member, f"{role.value} should be permitted to {guard}"
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)
