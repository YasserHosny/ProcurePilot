"""POST /auth/refresh — renews an expired session from its refresh token (demo finding 29)."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from procurepilot_api.errors import AuthenticationError
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.service import get_auth_service
from procurepilot_api.modules.members.models import Me, SessionResponse
from procurepilot_api.modules.tenants.models import Tenant
from procurepilot_api.shared.rate_limit import limiter

TENANT_ID = uuid4()


class FakeAuthService:
    calls: list[str] = []

    def reissue_session(self, *, refresh_token: str) -> SessionResponse:
        FakeAuthService.calls.append(refresh_token)
        if refresh_token != "good-refresh":
            raise AuthenticationError(details={"reason": "session_refresh_failed"})
        return SessionResponse(
            access_token="new-access",
            refresh_token="rotated-refresh",
            expires_in=3600,
            user=Me(
                id=uuid4(),
                email="buyer@example.test",
                role=MemberRole.buyer,
                mfa_enabled=False,
                tenant=Tenant(
                    id=TENANT_ID,
                    name="Example",
                    slug="example",
                    region="eg",
                    currency="EGP",
                    tax_model="exclusive",
                    default_locale="ar",
                ),
            ),
        )


@pytest.fixture
def client() -> TestClient:
    FakeAuthService.calls = []
    limiter.reset()
    app: FastAPI = create_app()
    app.dependency_overrides[get_auth_service] = FakeAuthService
    return TestClient(app)


def test_refresh_needs_no_bearer_and_returns_a_session(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "good-refresh"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "new-access"
    assert body["refresh_token"] == "rotated-refresh"
    assert body["user"]["tenant"]["id"] == str(TENANT_ID)
    assert FakeAuthService.calls == ["good-refresh"]


def test_rejected_refresh_token_is_401_unauthenticated(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "spent"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.unauthenticated"


@pytest.mark.parametrize("body", [{}, {"refresh_token": ""}])
def test_missing_refresh_token_is_rejected_before_supabase(
    client: TestClient, body: dict[str, str]
) -> None:
    response = client.post("/api/v1/auth/refresh", json=body)

    assert response.status_code == 422
    assert FakeAuthService.calls == []


def test_tenant_cannot_be_chosen_by_the_caller(client: TestClient) -> None:
    # Extra fields are ignored: the tenant comes only from the token the hook issues.
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "good-refresh", "tenant_id": str(uuid4())},
    )

    assert response.status_code == 200
    assert response.json()["user"]["tenant"]["id"] == str(TENANT_ID)


def test_refresh_shares_the_auth_rate_limit(client: TestClient) -> None:
    # conftest sets RATE_LIMIT_AUTH=10/minute; the 11th call inside the window is refused.
    statuses = [
        client.post("/api/v1/auth/refresh", json={"refresh_token": "good-refresh"}).status_code
        for _ in range(11)
    ]
    limiter.reset()

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
    assert len(FakeAuthService.calls) == 10
