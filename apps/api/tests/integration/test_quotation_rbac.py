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
QUOTATION_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "presign-document-upload": WRITE_ROLES,
    "create-quotation": WRITE_ROLES,
    "trigger-extraction": WRITE_ROLES,
    "correct-extracted-fields": WRITE_ROLES,
    "confirm-quotation": WRITE_ROLES,
    "read-document": ALL_ROLES,
    "read-quotation": ALL_ROLES,
    "read-job": ALL_ROLES,
    "read-review-tasks": ALL_ROLES,
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
@pytest.mark.parametrize("guard", sorted(QUOTATION_GUARDS), ids=sorted(QUOTATION_GUARDS))
def test_quotation_role_matrix_holds_in_both_directions(guard: str, role: MemberRole) -> None:
    dependency = require_role(*QUOTATION_GUARDS[guard])
    member = member_with_role(role)
    permitted = role in QUOTATION_GUARDS[guard]
    if permitted:
        assert dependency(member) == member
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)


def test_every_quotation_role_is_covered() -> None:
    assert set(ALL_ROLES) == set(MemberRole)
