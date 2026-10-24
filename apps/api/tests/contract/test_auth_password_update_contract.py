"""POST /auth/password-update — sets a new password from the emailed recovery link (PP-28)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from procurepilot_api.errors import AuthenticationError
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.service import get_auth_service
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.rate_limit import limiter


class FakeAuthService:
    calls: list[tuple[str, str, str]] = []

    def update_password(self, *, access_token: str, refresh_token: str, password: str) -> str:
        FakeAuthService.calls.append((access_token, refresh_token, password))
        if access_token != "recovery-access":
            raise AuthenticationError(details={"reason": "recovery_link_invalid"})
        return "buyer@example.test"


class FakeAuditWriter:
    events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate) -> None:
        FakeAuditWriter.events.append(event)


@pytest.fixture
def client() -> TestClient:
    FakeAuthService.calls = []
    FakeAuditWriter.events = []
    limiter.reset()
    app: FastAPI = create_app()
    app.dependency_overrides[get_auth_service] = FakeAuthService
    app.dependency_overrides[get_audit_writer] = FakeAuditWriter
    return TestClient(app)


def _body(**overrides: str) -> dict[str, str]:
    return {
        "access_token": "recovery-access",
        "refresh_token": "recovery-refresh",
        "password": "a-new-long-password",
    } | overrides


def test_recovery_session_sets_the_password_and_is_audited(client: TestClient) -> None:
    response = client.post("/api/v1/auth/password-update", json=_body())

    assert response.status_code == 204
    assert FakeAuthService.calls == [("recovery-access", "recovery-refresh", "a-new-long-password")]
    [event] = FakeAuditWriter.events
    assert event.action == "auth.password_reset_completed"
    assert event.actor_email == "buyer@example.test"
    assert event.outcome == "success"


def test_invalid_recovery_link_is_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/password-update", json=_body(access_token="stale"))

    assert response.status_code == 401
    assert response.json()["code"] == "auth.unauthenticated"
    assert FakeAuditWriter.events == []


@pytest.mark.parametrize(
    "body",
    [
        _body(password="too-short"),
        _body(access_token=""),
        _body(refresh_token=""),
        {"password": "a-new-long-password"},
    ],
)
def test_bad_request_is_rejected_before_supabase(client: TestClient, body: dict[str, str]) -> None:
    response = client.post("/api/v1/auth/password-update", json=body)

    assert response.status_code == 422
    assert FakeAuthService.calls == []
