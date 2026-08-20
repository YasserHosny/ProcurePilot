from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

ALL_ROLES: tuple[MemberRole, ...] = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)

WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)
CATALOGUE_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "create-product": WRITE_ROLES,
    "update-product": WRITE_ROLES,
    "archive-product": WRITE_ROLES,
    "add-substitute": WRITE_ROLES,
    "create-supplier": WRITE_ROLES,
    "update-supplier": WRITE_ROLES,
    "archive-supplier": WRITE_ROLES,
    "create-alias": WRITE_ROLES,
    "remove-alias": WRITE_ROLES,
    "read-products": ALL_ROLES,
    "read-suppliers": ALL_ROLES,
    "read-aliases": ALL_ROLES,
}


def member_with_role(role: MemberRole) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="member@example.test",
        role=role,
    )


@pytest.mark.parametrize("role", ALL_ROLES, ids=[role.value for role in ALL_ROLES])
@pytest.mark.parametrize("guard", sorted(CATALOGUE_GUARDS), ids=sorted(CATALOGUE_GUARDS))
def test_catalogue_role_matrix_holds_in_both_directions(
    guard: str,
    role: MemberRole,
) -> None:
    dependency = require_role(*CATALOGUE_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in CATALOGUE_GUARDS[guard]
    if permitted:
        assert dependency(member) == member, f"{role.value} should be permitted to {guard}"
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)


def test_every_catalogue_role_is_covered() -> None:
    assert set(ALL_ROLES) == set(MemberRole)
