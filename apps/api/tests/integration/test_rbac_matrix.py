"""Role enforcement, every role against every guard — task T051 (FR-013, SC-004).

SC-004 requires 100% of role-restricted actions to be refused for roles that do not hold them,
verified for EVERY role. So this is a matrix, not a sample: each of the five roles is tried
against each guard, and both halves are asserted — that permitted roles get through, and that
every other role is refused.

The frontend also hides actions a role cannot perform, but that is a display convenience. This is
the control (research R9). A test that only checked the happy path would let a guard that
accidentally allows everyone pass.
"""

# NOTE: deliberately no `from __future__ import annotations` here. It turns annotations into
# strings, and FastAPI then cannot resolve `Annotated[CurrentMember, Depends(...)]` inside the
# nested route factories below — every route silently degrades to treating the dependency as a
# query parameter and answers 422 instead of 200/403.

from collections.abc import Callable
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

ALL_ROLES: tuple[MemberRole, ...] = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)

# The authority model as the spec states it. Owner-only today; the procurement permissions these
# roles will govern arrive with the features themselves in chunks 4.2-4.6.
GUARDS: dict[str, tuple[MemberRole, ...]] = {
    "invite-member": (MemberRole.owner,),
    "change-role": (MemberRole.owner,),
    "remove-member": (MemberRole.owner,),
    "update-workspace": (MemberRole.owner,),
    "read-anything": ALL_ROLES,
}


def build_app(role: MemberRole) -> FastAPI:
    """An app whose current member holds exactly `role`, with one route per guard."""
    app = FastAPI()
    register_exception_handlers(app)

    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="member@example.test",
        role=role,
    )

    for name, allowed in GUARDS.items():
        def make_route(
            allowed_roles: tuple[MemberRole, ...],
        ) -> Callable[..., dict[str, bool]]:
            def route(
                _member: Annotated[CurrentMember, Depends(require_role(*allowed_roles))],
            ) -> dict[str, bool]:
                return {"allowed": True}

            return route

        app.get(f"/{name}")(make_route(allowed))

    app.dependency_overrides[current_member] = lambda: member
    return app


@pytest.mark.parametrize("role", ALL_ROLES, ids=[r.value for r in ALL_ROLES])
@pytest.mark.parametrize("guard", sorted(GUARDS), ids=sorted(GUARDS))
def test_the_role_matrix_holds_in_both_directions(guard: str, role: MemberRole) -> None:
    client = TestClient(build_app(role), raise_server_exceptions=False)
    response = client.get(f"/{guard}")

    permitted = role in GUARDS[guard]
    if permitted:
        assert response.status_code == 200, (
            f"{role.value} should be permitted to {guard} but got {response.status_code}"
        )
    else:
        assert response.status_code == 403, (
            f"{role.value} must NOT be permitted to {guard} but got {response.status_code}"
        )


@pytest.mark.parametrize("role", ALL_ROLES, ids=[r.value for r in ALL_ROLES])
def test_a_refusal_carries_the_error_envelope(role: MemberRole) -> None:
    """A refusal must be actionable, not a bare 403 — FR-013 asks for a clear explanation."""
    if role is MemberRole.owner:
        pytest.skip("owner is permitted; there is no refusal to inspect")

    client = TestClient(build_app(role), raise_server_exceptions=False)
    body = client.get("/invite-member").json()

    assert body["code"]
    assert body["message"]
    assert body["trace_id"]


def test_every_role_is_covered_by_the_matrix() -> None:
    """Guards the matrix itself: adding a role without extending this test must fail here."""
    assert set(ALL_ROLES) == set(MemberRole), (
        "MemberRole gained a value that the RBAC matrix does not exercise"
    )
