from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr

from procurepilot_api.modules.accounting.sync_service import (
    SyncService,
    TokenRefreshFailedError,
)
from procurepilot_api.modules.accounting.xero_client import XeroAuthError

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000004")


class _Cursor:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row
        self.queries: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.queries.append((query, params))

    def fetchone(self) -> dict[str, object] | None:
        return self.row

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


class _XeroConnector:
    def list_vendors(self) -> list[object]:
        raise XeroAuthError(
            "Xero API request unauthorized (401): safe-code",
            status_code=401,
            error_code="safe-code",
        )


def test_xero_vendor_auth_failure_marks_connection_and_records_safe_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        accounting_provider_mode="xero",
        database_url=SecretStr("postgresql://unused"),
        accounting_token_encryption_key=None,
    )
    service_role_cursor = _Cursor(
        {"access_token": "encrypted-access", "refresh_token": "encrypted-refresh"}
    )
    worker_cursor = _Cursor()
    worker_connection = _Connection(worker_cursor)
    audit_events: list[dict[str, object]] = []

    @contextmanager
    def service_role_db(_settings: object) -> Iterator[_Connection]:
        yield _Connection(service_role_cursor)

    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service._service_role_db",
        service_role_db,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.psycopg.connect",
        lambda *_args, **_kwargs: worker_connection,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service._record_audit",
        lambda **kwargs: audit_events.append(kwargs),
    )
    service = SyncService()

    with pytest.raises(TokenRefreshFailedError, match="vendor_fetch") as error_info:
        service._run_sync_pipeline(
            settings=settings,
            tenant_id=TENANT_ID,
            connection_id=CONNECTION_ID,
            conn_row={
                "provider": "xero",
                "realm_id": "xero-tenant",
                "connected_at": datetime(2026, 9, 19),
                "last_synced_at": None,
            },
            connector_override=_XeroConnector(),
        )

    assert "safe-code" not in str(error_info.value)
    assert any(
        "update accounting_connection" in query.lower()
        for query, _ in worker_cursor.queries
    )
    assert audit_events == [
        {
            "tenant_id": TENANT_ID,
            "action": "accounting.sync_failed",
            "target": {
                "accounting_connection_id": str(CONNECTION_ID),
                "error": "provider_authentication_failed",
                "reason": "vendor_fetch_failed",
            },
            "outcome": "refused",
        }
    ]
