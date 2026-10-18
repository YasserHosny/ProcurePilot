"""A completion that loses the one-active-connection unique-index race returns 409, not 503.

Both connection services share the offers module's ``_authenticated_db``, which rewraps every
psycopg error as ServiceUnavailableError; the real wrapper is used here, over a fake connection.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import psycopg
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.accounting import service as accounting_service
from procurepilot_api.modules.accounting.connector import CompanyInfo, OAuthTokens
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers import service as offers_service
from procurepilot_api.modules.pos import service as pos_service

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000002")


def _member() -> CurrentMember:
    return CurrentMember(
        tenant_id=TENANT_ID,
        membership_id=MEMBERSHIP_ID,
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        email="owner@example.test",
        role=MemberRole.owner,
    )


class _Cursor:
    def __init__(self, insert_error: Exception) -> None:
        self.insert_error = insert_error

    def execute(self, query: str, _params: object = None) -> None:
        if query.lstrip().lower().startswith("insert"):
            raise self.insert_error

    def fetchone(self) -> None:
        return None  # the pre-check sees no active connection

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _Connection:
    def __init__(self, insert_error: Exception) -> None:
        self.insert_error = insert_error

    def cursor(self, **_kwargs: object) -> _Cursor:
        return _Cursor(self.insert_error)

    def commit(self) -> None:
        pass

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


def _settings() -> SimpleNamespace:
    key = SecretStr(Fernet.generate_key().decode())
    return SimpleNamespace(
        database_url=SecretStr("postgresql://unused"),
        accounting_provider_mode="quickbooks",
        quickbooks_redirect_uri="https://quickbooks.example.test/callback",
        xero_redirect_uri="https://xero.example.test/callback",
        accounting_token_encryption_key=key,
        square_redirect_uri="https://square.example.test/callback",
        pos_token_encryption_key=key,
    )


class _AccountingConnector:
    def exchange_code_for_tokens(self, **_kwargs: object) -> OAuthTokens:
        return OAuthTokens(access_token="access", refresh_token="refresh")

    def company_info(self) -> CompanyInfo:
        return CompanyInfo("realm-1", "Co")


class _PosConnector:
    def exchange_code_for_tokens(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(access_token="access", refresh_token="refresh", merchant_id="m-1")

    def get_account_info(self) -> SimpleNamespace:
        return SimpleNamespace(external_account_id="m-1", external_account_name="Shop")


def _complete(
    monkeypatch: pytest.MonkeyPatch, which: str, insert_error: Exception
) -> dict[str, object]:
    monkeypatch.setattr(offers_service.db, "connect", lambda _dsn: _Connection(insert_error))
    payload = {
        "tenant_id": str(TENANT_ID),
        "membership_id": str(MEMBERSHIP_ID),
        "provider": "quickbooks",
        "mode": "quickbooks",
    }
    if which == "accounting":
        monkeypatch.setattr(accounting_service, "verify_state", lambda *_a, **_k: payload)
        monkeypatch.setattr(
            accounting_service,
            "get_accounting_connector",
            lambda *_a, **_k: _AccountingConnector(),
        )
        return accounting_service.ConnectionService(_settings()).complete_connection(  # type: ignore[arg-type]
            _member(), state="state", code="code", realm_id="realm-1"
        )
    monkeypatch.setattr(pos_service, "verify_state", lambda *_a, **_k: payload)
    monkeypatch.setattr(pos_service, "get_pos_connector", lambda *_a, **_k: _PosConnector())
    return pos_service.ConnectionService(_settings()).complete_connection(  # type: ignore[arg-type]
        _member(), state="state", code="code"
    )


@pytest.mark.parametrize("which", ["accounting", "pos"])
def test_losing_the_unique_index_race_is_a_conflict(
    monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    with pytest.raises(ConflictError) as exc_info:
        _complete(monkeypatch, which, psycopg.errors.UniqueViolation("duplicate key"))
    assert exc_info.value.details["reason"] == "connection_already_exists"


@pytest.mark.parametrize("which", ["accounting", "pos"])
def test_other_database_errors_stay_service_unavailable(
    monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    with pytest.raises(ServiceUnavailableError):
        _complete(monkeypatch, which, psycopg.OperationalError("connection lost"))
