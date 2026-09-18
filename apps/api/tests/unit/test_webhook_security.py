from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from procurepilot_api.config import Settings
from procurepilot_api.errors import AuthenticationError
from procurepilot_api.modules.ingestion.webhook_security import (
    verify_mailgun_signature,
    verify_shared_secret,
)

_SIGNING_KEY = "test-signing-key"
_SHARED_SECRET = "test-shared-secret"


@pytest.fixture(autouse=True)
def _webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILGUN_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.setenv("INGESTION_WEBHOOK_SHARED_SECRET", _SHARED_SECRET)


def _sign(timestamp: str, token: str) -> str:
    return hmac.new(
        _SIGNING_KEY.encode("utf-8"), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()


def test_verify_mailgun_signature_accepts_a_valid_fresh_signature() -> None:
    settings = Settings()
    timestamp = str(int(time.time()))
    token = "abc123"

    verify_mailgun_signature(
        settings, timestamp=timestamp, token=token, signature=_sign(timestamp, token)
    )


def test_verify_mailgun_signature_rejects_a_wrong_signature() -> None:
    settings = Settings()
    timestamp = str(int(time.time()))

    with pytest.raises(AuthenticationError) as exc:
        verify_mailgun_signature(settings, timestamp=timestamp, token="abc123", signature="wrong")
    assert exc.value.details["reason"] == "invalid_mailgun_signature"


def test_verify_mailgun_signature_rejects_when_signing_key_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MAILGUN_SIGNING_KEY", raising=False)
    settings = Settings()

    with pytest.raises(AuthenticationError) as exc:
        verify_mailgun_signature(settings, timestamp="123", token="abc", signature="sig")
    assert exc.value.details["reason"] == "mailgun_signing_key_not_configured"


def test_verify_mailgun_signature_rejects_a_stale_timestamp_even_with_a_valid_signature() -> None:
    """R3.0 security review (T042): a captured valid webhook call must not be replayable
    forever. A signature computed correctly over an old timestamp is still rejected."""
    settings = Settings()
    stale_timestamp = str(int(time.time()) - 3600)  # 1 hour old, well past the 900s default
    token = "abc123"

    with pytest.raises(AuthenticationError) as exc:
        verify_mailgun_signature(
            settings,
            timestamp=stale_timestamp,
            token=token,
            signature=_sign(stale_timestamp, token),
        )
    assert exc.value.details["reason"] == "stale_mailgun_timestamp"


def test_verify_mailgun_signature_rejects_a_future_timestamp_beyond_skew() -> None:
    settings = Settings()
    future_timestamp = str(int(time.time()) + 3600)
    token = "abc123"

    with pytest.raises(AuthenticationError) as exc:
        verify_mailgun_signature(
            settings,
            timestamp=future_timestamp,
            token=token,
            signature=_sign(future_timestamp, token),
        )
    assert exc.value.details["reason"] == "stale_mailgun_timestamp"


def test_verify_mailgun_signature_accepts_a_timestamp_just_inside_the_skew_window() -> None:
    settings = Settings()
    timestamp = str(int(time.time()) - 800)  # inside the 900s default window
    token = "abc123"

    verify_mailgun_signature(
        settings, timestamp=timestamp, token=token, signature=_sign(timestamp, token)
    )


def test_verify_mailgun_signature_rejects_a_non_numeric_timestamp() -> None:
    """A forged or malformed timestamp must not crash the handler or bypass the freshness
    check by accident - it's rejected explicitly, distinctly from a stale-but-parseable one."""
    settings = Settings()
    token = "abc123"
    timestamp = "not-a-number"

    with pytest.raises(AuthenticationError) as exc:
        verify_mailgun_signature(
            settings, timestamp=timestamp, token=token, signature=_sign(timestamp, token)
        )
    assert exc.value.details["reason"] == "invalid_mailgun_timestamp"


def test_verify_shared_secret_accepts_the_configured_secret() -> None:
    settings = Settings()
    verify_shared_secret(settings, provided_secret=_SHARED_SECRET)


def test_verify_shared_secret_rejects_a_wrong_secret() -> None:
    settings = Settings()
    with pytest.raises(AuthenticationError) as exc:
        verify_shared_secret(settings, provided_secret="wrong-secret")
    assert exc.value.details["reason"] == "invalid_webhook_secret"


def test_verify_shared_secret_rejects_a_missing_secret() -> None:
    settings = Settings()
    with pytest.raises(AuthenticationError) as exc:
        verify_shared_secret(settings, provided_secret=None)
    assert exc.value.details["reason"] == "invalid_webhook_secret"


def test_verify_shared_secret_rejects_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INGESTION_WEBHOOK_SHARED_SECRET", raising=False)
    settings = Settings()
    with pytest.raises(AuthenticationError) as exc:
        verify_shared_secret(settings, provided_secret="anything")
    assert exc.value.details["reason"] == "ingestion_webhook_secret_not_configured"
