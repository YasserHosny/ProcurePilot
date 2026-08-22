from __future__ import annotations

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
SMART_COMPARE_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "read-offers": ALL_ROLES,
    "read-compare": ALL_ROLES,
    "read-price-history": ALL_ROLES,
    "read-basket-job": ALL_ROLES,
    "read-alerts": ALL_ROLES,
    "submit-basket": WRITE_ROLES,
    "dismiss-alert": WRITE_ROLES,
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
@pytest.mark.parametrize("guard", sorted(SMART_COMPARE_GUARDS), ids=sorted(SMART_COMPARE_GUARDS))
def test_smart_compare_role_matrix_holds_in_both_directions(
    guard: str,
    role: MemberRole,
) -> None:
    dependency = require_role(*SMART_COMPARE_GUARDS[guard])
    member = member_with_role(role)
    if role in SMART_COMPARE_GUARDS[guard]:
        assert dependency(member) == member
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)


def test_every_smart_compare_role_is_covered() -> None:
    assert set(ALL_ROLES) == set(MemberRole)
