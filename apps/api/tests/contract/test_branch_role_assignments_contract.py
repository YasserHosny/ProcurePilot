"""Branch role assignment contract and DB-level proof — task T035 (007-organisation-model, US4).

Two things this file deliberately does NOT prove, and why:

- The 422 "member_id does not currently hold a branch-scopable role" check and the 404s for a
  missing membership/branch are pure Python logic in MemberService.create_branch_role_assignment
  (a live fetch-then-check, not a database constraint) — there is nothing here for a schema test
  or a raw-SQL test to exercise. This was verified directly via a live HTTP round-trip against
  the real running API before this file was committed (see the T035 commit message), matching
  this codebase's established pattern for confirm_dependents/orphan-flagging/overlap_warning:
  pure application logic gets its full HTTP-level proof from a live check, not a pytest file that
  would otherwise need to fake the entire supabase-py client this codebase has no precedent for.
- The 409 on a duplicate assignment IS a real database guarantee (the table's own
  `unique (tenant_id, membership_id, branch_id)` constraint) — proven directly below.
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
from pydantic import ValidationError

from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.organisation.schemas import (
    BranchRoleAssignment,
    BranchRoleAssignmentCreate,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs a Postgres with the organisation migrations applied",
)


def test_branch_role_assignment_contract_accepts_the_full_shape() -> None:
    assignment = BranchRoleAssignment(
        id=uuid4(),
        membership_id=uuid4(),
        branch_id=uuid4(),
        created_at="2026-08-22T00:00:00Z",
    )
    assert assignment.membership_id is not None


def test_branch_role_assignment_create_requires_both_ids() -> None:
    with pytest.raises(ValidationError):
        BranchRoleAssignmentCreate.model_validate({"membership_id": str(uuid4())})
    with pytest.raises(ValidationError):
        BranchRoleAssignmentCreate.model_validate({"branch_id": str(uuid4())})


def test_branch_role_assignment_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        BranchRoleAssignmentCreate.model_validate(
            {"membership_id": str(uuid4()), "branch_id": str(uuid4()), "role": "owner"}
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


def test_a_duplicate_assignment_is_rejected_by_the_database(conn: object) -> None:
    """The 409 the API maps this to is real: `unique (tenant_id, membership_id, branch_id)`,
    not application-layer validation alone."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "assignment-duplicate")
        act_as(cur, workspace)
        branch_id = make_branch(cur, workspace)
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (uuid4(), workspace.tenant_id, workspace.membership_id, branch_id),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
                "values (%s,%s,%s,%s)",
                (uuid4(), workspace.tenant_id, workspace.membership_id, branch_id),
            )


def test_the_same_member_may_be_assigned_to_a_different_branch(conn: object) -> None:
    """The unique constraint is per (membership, branch), not per membership alone — a member
    scoped to multiple branches is supported as separate rows (research.md R2)."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "assignment-multi-branch")
        act_as(cur, workspace)
        first_branch = make_branch(cur, workspace, name="First Branch")
        second_branch = make_branch(cur, workspace, name="Second Branch")
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (uuid4(), workspace.tenant_id, workspace.membership_id, first_branch),
        )
        # Must not raise — same member, different branch.
        cur.execute(
            "insert into branch_role_assignment (id,tenant_id,membership_id,branch_id) "
            "values (%s,%s,%s,%s)",
            (uuid4(), workspace.tenant_id, workspace.membership_id, second_branch),
        )
        cur.execute(
            "select count(*) from branch_role_assignment where membership_id = %s",
            (workspace.membership_id,),
        )
        assert cur.fetchone() == (2,)


# --- owner-only write access (matches test_branches.py's direct require_role() style) -------

WRITE_ROLES = (MemberRole.owner,)
ASSIGNMENT_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "create-branch-role-assignment": WRITE_ROLES,
    "remove-branch-role-assignment": WRITE_ROLES,
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


@pytest.mark.parametrize(
    "role",
    (
        MemberRole.owner,
        MemberRole.buyer,
        MemberRole.branch_manager,
        MemberRole.approver,
        MemberRole.viewer,
    ),
    ids=lambda r: r.value,
)
@pytest.mark.parametrize("guard", sorted(ASSIGNMENT_GUARDS), ids=sorted(ASSIGNMENT_GUARDS))
def test_branch_role_assignment_matrix_holds_in_both_directions(
    guard: str, role: MemberRole
) -> None:
    dependency = require_role(*ASSIGNMENT_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in ASSIGNMENT_GUARDS[guard]
    if permitted:
        assert dependency(member) == member, f"{role.value} should be permitted to {guard}"
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)
