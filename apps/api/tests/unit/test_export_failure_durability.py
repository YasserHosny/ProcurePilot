from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.workers import export_worker


class _Cursor:
    def __init__(self, conn: object, row: dict[str, object] | None = None) -> None:
        self.conn = conn
        self.row = row

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.conn.statements.append((sql, params))
        if "update export_job" in sql and "status = 'failed'" in sql:
            self.conn.failed_marked = True

    def fetchone(self) -> dict[str, object] | None:
        return self.row


class _Conn:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row
        self.statements: list[tuple[str, object]] = []
        self.failed_marked = False
        self.committed_after_failed = False

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self, **_kwargs: object) -> _Cursor:
        return _Cursor(self, self.row)

    def commit(self) -> None:
        if self.failed_marked:
            self.committed_after_failed = True


def _member(tenant_id: UUID) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=tenant_id,
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def test_export_enqueue_failure_marks_failed_and_commits_before_reraising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    job_id = uuid4()
    conn = _Conn(
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "kind": "savings_ledger",
            "format": "xlsx",
            "filters": {"period_start": "2026-08-01", "period_end": "2026-08-31"},
            "status": "queued",
            "created_at": datetime.now(UTC),
            # The same stub row also answers create_job's workspace_context lookup.
            "reporting_timezone": "UTC",
            "preferred_locale": None,
            "default_locale": "en",
        }
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.service._authenticated_db",
        lambda *_args, **_kwargs: conn,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.service._enforce_row_cap",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.service._enqueue_export_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ServiceUnavailableError(details={"dependency": "redis"})
        ),
    )

    with pytest.raises(ServiceUnavailableError):
        ExportService(settings=type("Settings", (), {"export_row_cap": 10_000})()).create_job(
            member=_member(tenant_id),
            payload=ExportCreate(
                kind="savings_ledger",
                format="xlsx",
                filters=ExportFilters(period_start="2026-08-01", period_end="2026-08-31"),
            ),
        )

    assert conn.failed_marked
    assert conn.committed_after_failed


def test_worker_failure_mark_is_committed_before_exception_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    job_id = uuid4()
    conn = _Conn()

    class _Psycopg:
        @staticmethod
        def connect(*_args: object, **_kwargs: object) -> _Conn:
            return conn

    class _Settings:
        database_url = type("Secret", (), {"get_secret_value": lambda self: "postgres://test"})()

    monkeypatch.setattr(export_worker, "psycopg", _Psycopg)

    export_worker._persist_failure(
        _Settings(),
        tenant_id=tenant_id,
        job_id=job_id,
        exc=RuntimeError("forced"),
    )

    assert conn.failed_marked
    assert conn.committed_after_failed
