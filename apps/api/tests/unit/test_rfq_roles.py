"""Only an owner or buyer creates, edits, sends, or prepares from an RFQ (spec 021 FR-001/FR-003).

Security review 2026-10-18 (issue #122): these routes resolved only `current_member`, so a
viewer, approver or branch manager could create and send real supplier emails.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq.service import get_rfq_service

RFQ_ID = uuid4()
ROUTES = [
    ("post", "/api/v1/rfq"),
    ("put", f"/api/v1/rfq/{RFQ_ID}"),
    ("post", f"/api/v1/rfq/{RFQ_ID}/send"),
    ("post", f"/api/v1/rfq/{RFQ_ID}/prepare-request"),
]


def _client(role: MemberRole) -> TestClient:
    app = create_app()
    app.dependency_overrides[current_member] = lambda: CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email=f"{role.value}@example.test",
        role=role,
    )
    app.dependency_overrides[get_rfq_service] = lambda: object()
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "role", [MemberRole.viewer, MemberRole.approver, MemberRole.branch_manager]
)
@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_other_roles_are_refused(role: MemberRole, method: str, path: str) -> None:
    with _client(role) as client:
        response = client.request(
            method, path, json={}, headers={"Authorization": "Bearer test-token"}
        )
    assert response.status_code == 403


@pytest.mark.parametrize("role", [MemberRole.owner, MemberRole.buyer])
@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_owner_and_buyer_pass_the_role_check(role: MemberRole, method: str, path: str) -> None:
    with _client(role) as client:
        response = client.request(
            method, path, json={}, headers={"Authorization": "Bearer test-token"}
        )
    assert response.status_code != 403
