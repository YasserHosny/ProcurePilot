from __future__ import annotations

import hashlib
import hmac
import time

from procurepilot_api.config import Settings
from procurepilot_api.errors import AuthenticationError

# T014 (research R1: "pending implementation spike, start SES; fallback Mailgun"): signature
# verification per provider. Mailgun's HMAC scheme is fully implemented here — it needs no SDK
# and no network call. Full AWS SNS message verification (fetching and validating the X.509
# certificate chain for the topic that signed the notification) is a real, separate undertaking
# genuinely worth its own review once SES vs Mailgun is actually decided; "ses" mode is
# interim-verified against a configured shared secret instead of full chain validation, exactly
# like "stub" mode. Do not treat "ses" mode as production-hardened until that follow-up lands.


def verify_mailgun_signature(
    settings: Settings, *, timestamp: str, token: str, signature: str
) -> None:
    if settings.mailgun_signing_key is None:
        raise AuthenticationError(details={"reason": "mailgun_signing_key_not_configured"})
    signing_key = settings.mailgun_signing_key.get_secret_value().encode("utf-8")
    expected = hmac.new(
        signing_key, f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AuthenticationError(details={"reason": "invalid_mailgun_signature"})

    # R3.0 security review (T042): the HMAC alone proves Mailgun signed this exact
    # timestamp+token pair at some point — it says nothing about WHEN. Without this check, a
    # single captured valid webhook call stays replayable forever (message-id dedup downstream
    # stops a replay from creating a second quotation, but not from draining the tenant's daily
    # quota or creating another raw-email storage object each time). Checked only after the
    # signature itself verifies, so an attacker without the signing key learns nothing by probing
    # timestamps.
    try:
        signed_at = float(timestamp)
    except ValueError as exc:
        raise AuthenticationError(details={"reason": "invalid_mailgun_timestamp"}) from exc
    skew = abs(time.time() - signed_at)
    if skew > settings.mailgun_max_timestamp_skew_seconds:
        raise AuthenticationError(details={"reason": "stale_mailgun_timestamp"})


def verify_shared_secret(settings: Settings, *, provided_secret: str | None) -> None:
    """Interim verification for "stub" and "ses" modes: an opaque shared secret in a header or
    query param, checked with a constant-time comparison. Not a substitute for Mailgun's real
    HMAC or a real SNS signature — see the module docstring."""
    if settings.ingestion_webhook_shared_secret is None:
        raise AuthenticationError(details={"reason": "ingestion_webhook_secret_not_configured"})
    expected = settings.ingestion_webhook_shared_secret.get_secret_value()
    if not provided_secret or not hmac.compare_digest(expected, provided_secret):
        raise AuthenticationError(details={"reason": "invalid_webhook_secret"})
