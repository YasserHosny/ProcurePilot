from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole


def require_role(*roles: MemberRole) -> Callable[[CurrentMember], CurrentMember]:
    allowed_roles = frozenset(roles)

    def dependency(
        member: Annotated[CurrentMember, Depends(current_member)],
    ) -> CurrentMember:
        if member.role not in allowed_roles:
            raise PermissionDeniedError(details={"required_roles": sorted(allowed_roles)})
        return member

    return dependency
