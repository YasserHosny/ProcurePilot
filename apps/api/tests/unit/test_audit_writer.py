"""AuditWriter routing: a workspace event with no caller token goes over DATABASE_URL.

The anon key may no longer name a workspace in record_audit_event (migration
20261018000002), so server-side writers must not use it for tenant events.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from procurepilot_api.shared import audit as audit_module
from procurepilot_api.shared.audit import AuditEventCreate, AuditWriter


class _Recorder:
    def __init__(self) -> None:
        self.sql: list[tuple[str, tuple[Any, ...]]] = []
        self.rpc_calls: list[tuple[str | None, dict[str, Any]]] = []


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()

    class _Conn:
        def __enter__(self) -> _Conn:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[Any, ...]) -> None:
            rec.sql.append((sql, params))

    monkeypatch.setattr(audit_module.db, "connect", lambda *a, **k: _Conn())

    class _Rpc:
        def execute(self) -> None:
            return None

    class _Client:
        def __init__(self, bearer_token: str | None) -> None:
            self._bearer_token = bearer_token

        def rpc(self, name: str, params: dict[str, Any]) -> _Rpc:
            rec.rpc_calls.append((self._bearer_token, params))
            return _Rpc()

    def fake_client(self: AuditWriter, bearer_token: str | None) -> _Client:
        return _Client(bearer_token)

    monkeypatch.setattr(AuditWriter, "_client", fake_client)
    return rec


def _event(tenant: bool) -> AuditEventCreate:
    return AuditEventCreate(
        tenant_id=uuid4() if tenant else None,
        action="test.event",
        target={"k": "v"},
        outcome="success",
    )


def test_workspace_event_without_token_goes_over_database_url(recorder: _Recorder) -> None:
    event = _event(tenant=True)
    AuditWriter().record(event)
    assert recorder.rpc_calls == []
    assert len(recorder.sql) == 1
    sql, params = recorder.sql[0]
    assert "record_audit_event" in sql
    assert params[0] == "test.event"
    assert params[2] == str(event.tenant_id)


def test_workspace_event_with_token_uses_the_callers_claim(recorder: _Recorder) -> None:
    AuditWriter().record(_event(tenant=True), bearer_token="jwt")
    assert recorder.sql == []
    assert recorder.rpc_calls and recorder.rpc_calls[0][0] == "jwt"


def test_pre_authentication_event_stays_on_the_anon_client(recorder: _Recorder) -> None:
    AuditWriter().record(_event(tenant=False))
    assert recorder.sql == []
    assert recorder.rpc_calls and recorder.rpc_calls[0][0] is None
