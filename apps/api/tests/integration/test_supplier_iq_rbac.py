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
SUPPLIER_IQ_GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "read-supplier-terms": ALL_ROLES,
    "read-supplier-scorecard": ALL_ROLES,
    "read-anomaly-alerts": ALL_ROLES,
    "create-supplier-terms": WRITE_ROLES,
    "submit-advanced-basket": WRITE_ROLES,
    "dismiss-anomaly-alert": WRITE_ROLES,
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
@pytest.mark.parametrize("guard", sorted(SUPPLIER_IQ_GUARDS), ids=sorted(SUPPLIER_IQ_GUARDS))
def test_supplier_iq_role_matrix_holds_in_both_directions(
    guard: str,
    role: MemberRole,
) -> None:
    dependency = require_role(*SUPPLIER_IQ_GUARDS[guard])
    member = member_with_role(role)
    if role in SUPPLIER_IQ_GUARDS[guard]:
        assert dependency(member) == member
    else:
        with pytest.raises(PermissionDeniedError):
            dependency(member)


def test_every_supplier_iq_role_is_covered() -> None:
    assert set(ALL_ROLES) == set(MemberRole)
