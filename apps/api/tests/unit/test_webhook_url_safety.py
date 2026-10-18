"""Webhook endpoint URLs cannot reach internal addresses (security review 2026-10-18)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.webhooks.schemas import WebhookSubscriptionCreate
from procurepilot_api.modules.webhooks.service import WebhookService
from procurepilot_api.modules.webhooks.url_safety import validate_webhook_url

DISALLOWED = [
    "http://example.com",
    "https://127.0.0.1",
    "https://169.254.169.254",
    "https://10.0.0.1",
    "https://[::1]",
    "https://[::ffff:127.0.0.1]",
    "https://localhost",
    "https://user:pw@example.com",
]


def test_validator_accepts_https_example_com_hook() -> None:
    url = "https://example.com/hook"
    assert validate_webhook_url(url) == url


@pytest.mark.parametrize("url", DISALLOWED)
def test_validator_rejects_disallowed_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_webhook_url(url)


@pytest.mark.parametrize("url", DISALLOWED)
def test_create_subscription_refuses_disallowed_urls_with_422(url: str) -> None:
    test_key = Fernet.generate_key().decode()
    service = WebhookService(
        Settings(
            webhook_allow_private_endpoints=False,
            webhook_token_encryption_key=SecretStr(test_key),
        )
    )
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )
    with pytest.raises(UnprocessableEntityError):
        service.create_subscription(
            bearer_token="token",
            member=member,
            payload=WebhookSubscriptionCreate(endpoint_url=url),
        )


def test_escape_hatch_allows_private_endpoints() -> None:
    assert (
        validate_webhook_url("http://localhost:8000/hook", allow_private=True)
        == "http://localhost:8000/hook"
    )
    assert (
        validate_webhook_url("http://127.0.0.1:8000/hook", allow_private=True)
        == "http://127.0.0.1:8000/hook"
    )
    with pytest.raises(ValueError):
        validate_webhook_url("https://user:pw@example.com", allow_private=True)
