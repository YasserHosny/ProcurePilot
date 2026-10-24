"""Password reset: the emailed link opens the web app; its recovery session sets the password."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gotrue.errors import AuthApiError, AuthRetryableError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import (
    AuthenticationError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.service import AuthService


def _service(client: Mock, monkeypatch: pytest.MonkeyPatch, **overrides: object) -> AuthService:
    settings: Settings = get_settings().model_copy(update=overrides)
    service = AuthService(settings)
    monkeypatch.setattr(service, "_client", lambda: client)
    return service


def test_reset_email_links_to_the_web_app_set_password_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    service = _service(client, monkeypatch, web_origin="https://procurepilot.example.test/")

    service.request_password_reset(email="buyer@example.test")

    client.auth.reset_password_email.assert_called_once_with(
        "buyer@example.test",
        {"redirect_to": "https://procurepilot.example.test/auth/update-password"},
    )


def test_reset_email_falls_back_to_the_first_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    service = _service(
        client,
        monkeypatch,
        web_origin=None,
        api_cors_origins=("http://localhost:4200", "http://localhost:4300"),
    )

    service.request_password_reset(email="buyer@example.test")

    client.auth.reset_password_email.assert_called_once_with(
        "buyer@example.test",
        {"redirect_to": "http://localhost:4200/auth/update-password"},
    )


def test_update_password_uses_the_recovery_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.auth.update_user.return_value = SimpleNamespace(
        user=SimpleNamespace(email="buyer@example.test")
    )
    service = _service(client, monkeypatch)

    email = service.update_password(
        access_token="recovery-access",
        refresh_token="recovery-refresh",
        password="a-new-long-password",
    )

    assert email == "buyer@example.test"
    client.auth.set_session.assert_called_once_with("recovery-access", "recovery-refresh")
    client.auth.update_user.assert_called_once_with({"password": "a-new-long-password"})


@pytest.mark.parametrize("status", [400, 401, 403])
def test_expired_or_used_link_is_unauthenticated(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = Mock()
    client.auth.set_session.side_effect = AuthApiError("expired", status, "session_not_found")
    service = _service(client, monkeypatch)

    with pytest.raises(AuthenticationError) as raised:
        service.update_password(access_token="a", refresh_token="r", password="a-new-long-password")

    assert raised.value.details == {"reason": "recovery_link_invalid"}


@pytest.mark.parametrize("code", ["same_password", "weak_password"])
def test_password_refused_by_supabase_is_unprocessable(
    code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = Mock()
    client.auth.update_user.side_effect = AuthApiError("refused", 422, code)
    service = _service(client, monkeypatch)

    with pytest.raises(UnprocessableEntityError) as raised:
        service.update_password(access_token="a", refresh_token="r", password="a-new-long-password")

    assert raised.value.details == {"reason": code}


@pytest.mark.parametrize(
    "error",
    [
        AuthApiError("rate limited", 429, "over_request_rate_limit"),
        AuthRetryableError("unavailable", 503),
        ConnectionError("offline"),
    ],
)
def test_transient_failure_is_unavailable(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = Mock()
    client.auth.update_user.side_effect = error
    service = _service(client, monkeypatch)

    with pytest.raises(ServiceUnavailableError):
        service.update_password(access_token="a", refresh_token="r", password="a-new-long-password")
