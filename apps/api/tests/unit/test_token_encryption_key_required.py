"""Tests verifying token encryption key requirements at startup and at rest."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember, MemberRole
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.webhooks.schemas import WebhookSubscriptionCreate
from procurepilot_api.modules.webhooks.service import WebhookService
from procurepilot_api.shared.token_crypto import decrypt_token


def _valid_key() -> str:
    return Fernet.generate_key().decode()


def test_pos_square_without_encryption_key_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(pos_provider_mode="square", pos_token_encryption_key=None)
    error_msg = str(exc_info.value)
    assert "POS_TOKEN_ENCRYPTION_KEY" in error_msg
    assert "square" in error_msg

    # Also verify empty string is treated as None
    with pytest.raises(ValidationError) as exc_info:
        Settings(pos_provider_mode="square", pos_token_encryption_key=SecretStr(""))
    assert "POS_TOKEN_ENCRYPTION_KEY" in str(exc_info.value)


@pytest.mark.parametrize("mode", ["quickbooks", "xero"])
def test_accounting_non_stub_without_encryption_key_raises_validation_error(mode: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(accounting_provider_mode=mode, accounting_token_encryption_key=None)
    error_msg = str(exc_info.value)
    assert "ACCOUNTING_TOKEN_ENCRYPTION_KEY" in error_msg
    assert mode in error_msg

    # Also verify empty string is treated as None
    with pytest.raises(ValidationError) as exc_info:
        Settings(accounting_provider_mode=mode, accounting_token_encryption_key=SecretStr(""))
    assert "ACCOUNTING_TOKEN_ENCRYPTION_KEY" in str(exc_info.value)


def test_stub_modes_without_keys_succeed() -> None:
    settings = Settings(
        pos_provider_mode="stub",
        accounting_provider_mode="stub",
        pos_token_encryption_key=None,
        accounting_token_encryption_key=None,
        webhook_token_encryption_key=None,
    )
    assert settings.pos_provider_mode == "stub"
    assert settings.accounting_provider_mode == "stub"
    assert settings.pos_token_encryption_key is None
    assert settings.accounting_token_encryption_key is None
    assert settings.webhook_token_encryption_key is None


def test_non_stub_modes_with_valid_keys_succeed() -> None:
    key_pos = _valid_key()
    key_qb = _valid_key()
    key_xero = _valid_key()
    key_webhook = _valid_key()

    pos_settings = Settings(
        pos_provider_mode="square",
        pos_token_encryption_key=SecretStr(key_pos),
    )
    assert pos_settings.pos_token_encryption_key is not None
    assert pos_settings.pos_token_encryption_key.get_secret_value() == key_pos

    qb_settings = Settings(
        accounting_provider_mode="quickbooks",
        accounting_token_encryption_key=SecretStr(key_qb),
    )
    assert qb_settings.accounting_token_encryption_key is not None
    assert qb_settings.accounting_token_encryption_key.get_secret_value() == key_qb

    xero_settings = Settings(
        accounting_provider_mode="xero",
        accounting_token_encryption_key=SecretStr(key_xero),
    )
    assert xero_settings.accounting_token_encryption_key is not None
    assert xero_settings.accounting_token_encryption_key.get_secret_value() == key_xero

    webhook_settings = Settings(
        webhook_token_encryption_key=SecretStr(key_webhook),
    )
    assert webhook_settings.webhook_token_encryption_key is not None
    assert webhook_settings.webhook_token_encryption_key.get_secret_value() == key_webhook


@pytest.mark.parametrize(
    ("field_name", "env_var_name"),
    [
        ("pos_token_encryption_key", "POS_TOKEN_ENCRYPTION_KEY"),
        ("accounting_token_encryption_key", "ACCOUNTING_TOKEN_ENCRYPTION_KEY"),
        ("webhook_token_encryption_key", "WEBHOOK_TOKEN_ENCRYPTION_KEY"),
    ],
)
def test_malformed_key_raises_validation_error_without_leaking_key(
    field_name: str, env_var_name: str
) -> None:
    malformed_key = "not-a-key"
    with pytest.raises(ValidationError) as exc_info:
        Settings(**{field_name: SecretStr(malformed_key)})

    # ValidationError must name the env var
    assert env_var_name in str(exc_info.value)
    # The message must NOT contain the malformed value
    error_dicts = exc_info.value.errors()
    assert len(error_dicts) > 0
    for err in error_dicts:
        assert malformed_key not in err["msg"]
    # And str(exc_info.value) does not leak the secret because it is masked as SecretStr
    assert malformed_key not in str(exc_info.value)


def test_webhook_create_subscription_without_key_raises_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_auth_client = MagicMock()
    monkeypatch.setattr(
        "procurepilot_api.modules.webhooks.service.authenticated_client",
        mock_auth_client,
    )
    settings = Settings(webhook_token_encryption_key=None)
    service = WebhookService(settings)
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )
    payload = WebhookSubscriptionCreate(endpoint_url="https://example.com/webhook")

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.create_subscription(bearer_token="token", member=member, payload=payload)

    assert exc_info.value.details == {"dependency": "webhook_encryption_key"}
    mock_auth_client.assert_not_called()


def test_webhook_create_subscription_with_key_encrypts_stored_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_key = _valid_key()
    settings = Settings(
        webhook_allow_private_endpoints=True,
        webhook_token_encryption_key=SecretStr(raw_key),
    )
    service = WebhookService(settings)
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )
    payload = WebhookSubscriptionCreate(endpoint_url="https://example.com/webhook")

    now = datetime.now(UTC).isoformat()
    sub_id = str(uuid4())
    mock_table = MagicMock()
    mock_insert = MagicMock()
    mock_select = MagicMock()
    mock_single = MagicMock()

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_insert.select.return_value = mock_select
    mock_select.single.return_value = mock_single
    mock_single.execute.return_value = MagicMock(
        data={
            "id": sub_id,
            "endpoint_url": "https://example.com/webhook",
            "events": ["quotation.created"],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )

    monkeypatch.setattr(
        "procurepilot_api.modules.webhooks.service.authenticated_client",
        lambda _settings, _token: mock_client,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.webhooks.service.get_audit_writer",
        lambda: MagicMock(),
    )

    created = service.create_subscription(bearer_token="token", member=member, payload=payload)

    # Database was called
    mock_table.insert.assert_called_once()
    inserted_row = mock_table.insert.call_args[0][0]

    # Secret stored in the database is encrypted, NOT the plaintext secret
    assert inserted_row["secret_encrypted"] != created.secret
    # Decrypting stored secret with key recovers the generated secret
    assert decrypt_token(inserted_row["secret_encrypted"], raw_key) == created.secret


def test_validation_error_from_environment_does_not_retain_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_role_secret = "service-role-secret-value-123"
    malformed_key = "malformed-key-material-456"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", service_role_secret)
    monkeypatch.setenv("POS_TOKEN_ENCRYPTION_KEY", malformed_key)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    error = exc_info.value
    assert "POS_TOKEN_ENCRYPTION_KEY" in str(error)
    rendered = " ".join(
        [str(error), repr(error), error.json(), repr(error.errors()), repr(error.__cause__)]
    )
    for secret in (service_role_secret, malformed_key):
        assert secret not in rendered
    assert all(err["input"] is None for err in error.errors())
    assert error.__context__ is None or error.__suppress_context__
