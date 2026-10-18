from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.invitations import get_member_invitation_service
from procurepilot_api.modules.members.models import MemberInvitation


class InvitationService:
    invitation_id = uuid4()

    def issue(
        self, *, bearer_token: str, member: CurrentMember, email: str, role: MemberRole
    ) -> MemberInvitation:
        assert bearer_token == "owner-token"
        return MemberInvitation(
            id=self.invitation_id,
            email=email,
            role=role,
            status="pending",
            expires_at=datetime.now(UTC),
            token="example-invitation-token",
            email_delivery="sent",
        )

    def resend(
        self, *, bearer_token: str, member: CurrentMember, invitation_id: UUID
    ) -> MemberInvitation:
        if invitation_id != self.invitation_id:
            raise NotFoundError(details={"resource": "invitation"})
        return self.issue(
            bearer_token=bearer_token,
            member=member,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )


@pytest.fixture
def app() -> FastAPI:
    app = create_app()
    app.dependency_overrides[bearer_token] = lambda: "owner-token"
    app.dependency_overrides[current_member] = lambda: member(MemberRole.owner)
    app.dependency_overrides[get_member_invitation_service] = InvitationService
    return app


def member(role: MemberRole) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=role,
    )


def test_issue_and_resend_contract(app: FastAPI) -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        for path, payload, status in [
            ("/api/v1/invitations", {"email": "buyer@example.test", "role": "buyer"}, 201),
            (f"/api/v1/invitations/{InvitationService.invitation_id}/resend", {}, 200),
        ]:
            response = client.post(path, json=payload)
            assert response.status_code == status, response.text
            assert response.json()["token"] == "example-invitation-token"
            assert response.json()["email_delivery"] == "sent"


@pytest.mark.parametrize(
    "path", ["/api/v1/invitations", f"/api/v1/invitations/{InvitationService.invitation_id}/resend"]
)
def test_invitation_mutations_require_owner(app: FastAPI, path: str) -> None:
    app.dependency_overrides[current_member] = lambda: member(MemberRole.buyer)
    with TestClient(app) as client:
        response = client.post(path, json={"email": "buyer@example.test", "role": "buyer"})
    assert response.status_code == 403


def test_resend_unknown_is_not_found_envelope(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post(f"/api/v1/invitations/{uuid4()}/resend")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "details", "trace_id"}


def test_resend_coalesced_conflict_envelope(app: FastAPI) -> None:
    class ConflictInvitationService(InvitationService):
        def resend(
            self, *, bearer_token: str, member: CurrentMember, invitation_id: UUID
        ) -> MemberInvitation:
            raise ConflictError(details={"reason": "resent_recently", "retry_after_seconds": 45})

    app.dependency_overrides[get_member_invitation_service] = ConflictInvitationService
    with TestClient(app) as client:
        response = client.post(f"/api/v1/invitations/{InvitationService.invitation_id}/resend")
    assert response.status_code == 409
    data = response.json()
    assert set(data) == {"code", "message", "details", "trace_id"}
    assert data["details"]["reason"] == "resent_recently"
    assert data["details"]["retry_after_seconds"] == 45
