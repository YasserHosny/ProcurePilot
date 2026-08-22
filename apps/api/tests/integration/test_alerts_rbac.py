from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.alerts.router import WRITE_ROLES
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role


def test_alert_dismissal_router_guard_rejects_non_write_role() -> None:
    viewer = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="viewer@example.test",
        role=MemberRole.viewer,
    )
    with pytest.raises(PermissionDeniedError):
        require_role(*WRITE_ROLES)(viewer)


@pytest.mark.parametrize("role", [MemberRole.owner, MemberRole.buyer])
def test_alert_dismissal_router_guard_allows_owner_and_buyer(role: MemberRole) -> None:
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email=f"{role.value}@example.test",
        role=role,
    )
    assert require_role(*WRITE_ROLES)(member) == member
