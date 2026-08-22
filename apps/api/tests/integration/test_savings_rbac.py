from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role


def _member(role: MemberRole) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email=f"{role.value}@example.test",
        role=role,
    )


def test_owner_and_buyer_may_record_verify_and_export() -> None:
    dependency = require_role(MemberRole.owner, MemberRole.buyer)

    assert dependency(_member(MemberRole.owner)).role == MemberRole.owner
    assert dependency(_member(MemberRole.buyer)).role == MemberRole.buyer


@pytest.mark.parametrize(
    "role",
    [MemberRole.branch_manager, MemberRole.approver, MemberRole.viewer],
)
def test_read_only_roles_cannot_mutate_savings_or_exports(role: MemberRole) -> None:
    dependency = require_role(MemberRole.owner, MemberRole.buyer)

    with pytest.raises(PermissionDeniedError):
        dependency(_member(role))
