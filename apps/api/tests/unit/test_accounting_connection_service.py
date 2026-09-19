from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from pydantic import SecretStr

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.accounting.connector import CompanyInfo, OAuthTokens
from procurepilot_api.modules.accounting.service import (
    ConnectionService,
    _verify_state,
)
from procurepilot_api.modules.auth.jwt import MemberRole

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000003")


def _member() -> CurrentMember:
    return CurrentMember(
        tenant_id=TENANT_ID,
        membership_id=MEMBERSHIP_ID,
        user_id=USER_ID,
        email="owner@example.test",
        role=MemberRole.owner,
    )


def _settings(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        accounting_provider_mode=mode,
        quickbooks_redirect_uri="https://quickbooks.example.test/callback",
        xero_redirect_uri="https://xero.example.test/callback",
        accounting_token_encryption_key=None,
        supabase_jwt_secret=SecretStr("state-secret"),
        supabase_service_role_key=SecretStr("service-secret"),
    )


class _Cursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.calls.append((query, params))

    def fetchone(self) -> dict[str, object] | None:
        if any("insert into accounting_connection" in query.lower() for query, _ in self.calls):
            return self.row
        return None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor

    def cursor(self, **_kwargs: object) -> _Cursor:
        return self.cursor_obj

    def commit(self) -> None:
        pass

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


class _Connector:
    def __init__(self, company: CompanyInfo) -> None:
        self.company = company
        self.exchange_args: dict[str, object] | None = None

    def build_authorization_url(self, state: str) -> str:
        return f"https://provider.example.test/authorize?state={state}"

    def exchange_code_for_tokens(self, **kwargs: object) -> OAuthTokens:
        self.exchange_args = kwargs
        return OAuthTokens(access_token="access", refresh_token="refresh")

    def company_info(self) -> CompanyInfo:
        return self.company


def test_start_connection_uses_xero_and_binds_provider_mode_in_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("xero")
    cursor = _Cursor({})
    connector = _Connector(CompanyInfo("verified-xero-tenant", "Xero Co"))

    @contextmanager
    def db(_settings: object, _member: CurrentMember) -> Iterator[_Connection]:
        yield _Connection(cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service._authenticated_db", db
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_accounting_connector",
        lambda configured: connector,
    )

    url = ConnectionService(settings).start_connection(_member())
    state = parse_qs(urlparse(url).query)["state"][0]
    payload = _verify_state(settings, state)

    assert payload is not None
    assert payload["provider"] == "xero"
    assert payload["mode"] == "xero"


def test_xero_callback_persists_verified_company_realm_and_uses_xero_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("xero")
    cursor = _Cursor(
        {
            "id": UUID("00000000-0000-0000-0000-000000000004"),
            "tenant_id": TENANT_ID,
            "provider": "xero",
            "realm_id": "verified-xero-tenant",
            "display_name": "Xero Co",
            "status": "active",
        }
    )
    connector = _Connector(CompanyInfo("verified-xero-tenant", "Xero Co"))

    @contextmanager
    def db(_settings: object, _member: CurrentMember) -> Iterator[_Connection]:
        yield _Connection(cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service._authenticated_db", db
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_accounting_connector",
        lambda configured, **kwargs: connector,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service._record_audit", lambda **kwargs: None
    )

    service = ConnectionService(settings)
    state = service.start_connection(_member())
    state = parse_qs(urlparse(state).query)["state"][0]
    result = service.complete_connection(
        state=state,
        code="xero-code",
        realm_id="untrusted-callback-value",
    )

    assert result is not None
    assert connector.exchange_args == {
        "code": "xero-code",
        "redirect_uri": "https://xero.example.test/callback",
        "realm_id": "untrusted-callback-value",
    }
    insert_params = next(
        params
        for query, params in cursor.calls
        if "insert into accounting_connection" in query.lower()
    )
    assert insert_params["provider"] == "xero"
    assert insert_params["realm_id"] == "verified-xero-tenant"


def test_callback_state_cannot_be_completed_after_provider_mode_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("xero")
    cursor = _Cursor({})
    connector_calls = 0

    def connector_factory(configured: object) -> _Connector:
        nonlocal connector_calls
        connector_calls += 1
        return _Connector(CompanyInfo("tenant", "Xero Co"))

    @contextmanager
    def db(_settings: object, _member: CurrentMember) -> Iterator[_Connection]:
        yield _Connection(cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service._authenticated_db", db
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_accounting_connector",
        connector_factory,
    )

    service = ConnectionService(settings)
    state_url = service.start_connection(_member())
    state = parse_qs(urlparse(state_url).query)["state"][0]
    settings.accounting_provider_mode = "quickbooks"

    assert (
        service.complete_connection(
            state=state,
            code="code",
            realm_id="valid-quickbooks-realm",
        )
        is None
    )

    # The effective provider is the same, but the signed mode still binds the callback.
    settings.accounting_provider_mode = "stub"
    stub_state_url = service.start_connection(_member())
    stub_state = parse_qs(urlparse(stub_state_url).query)["state"][0]
    settings.accounting_provider_mode = "quickbooks"
    assert (
        service.complete_connection(
            state=stub_state,
            code="code",
            realm_id="valid-quickbooks-realm",
        )
        is None
    )
    assert connector_calls == 2
    assert not any(
        "insert into accounting_connection" in query.lower() for query, _ in cursor.calls
    )
