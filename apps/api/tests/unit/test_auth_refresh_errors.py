"""Only a refused refresh token is an authentication failure."""

from unittest.mock import Mock

import pytest
from gotrue.errors import AuthApiError, AuthRetryableError

from procurepilot_api.errors import AuthenticationError, ServiceUnavailableError
from procurepilot_api.modules.auth.service import AuthService


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_refresh_rejection_is_unauthenticated(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.auth.refresh_session.side_effect = AuthApiError("refused", status, "invalid_credentials")
    service = AuthService()
    monkeypatch.setattr(service, "_client", lambda: client)

    with pytest.raises(AuthenticationError):
        service.reissue_session(refresh_token="spent")


@pytest.mark.parametrize(
    "error",
    [
        AuthApiError("rate limited", 429, "over_request_rate_limit"),
        AuthApiError("upstream failure", 500, "unexpected_failure"),
        AuthRetryableError("unavailable", 503),
        ConnectionError("offline"),
        ServiceUnavailableError(),
    ],
)
def test_transient_refresh_failure_is_unavailable(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = Mock()
    client.auth.refresh_session.side_effect = error
    service = AuthService()
    monkeypatch.setattr(service, "_client", lambda: client)

    with pytest.raises(ServiceUnavailableError):
        service.reissue_session(refresh_token="still-valid")
