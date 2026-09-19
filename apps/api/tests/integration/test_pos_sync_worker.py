"""Integration tests for the daily POS sync worker (R3.2, US2, task T026).

Covers:
- Concurrency proof: PostgreSQL advisory lock prevents duplicate sync claims (zero sleep race)
- Due gating: picks up null and >1-day last_synced_at, skips recent (<1 day) and non-active
- Resilience: per-connection exception handling continues past failures to process subsequent items
- Worker loop: run_loop(once=True) terminates cleanly
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.modules.pos.sync_service import SyncService
from procurepilot_api.shared.audit import AuditEventCreate
from procurepilot_api.workers.pos_sync_worker import run_loop, tick

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


def _clean_pos_tables() -> None:
    if TEST_DATABASE_URL:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("delete from pos_product_match")
                cur.execute("delete from synced_product_signal")
                cur.execute("delete from pos_connection")
            conn.commit()


@pytest.fixture(autouse=True)
def _mock_audit_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> RecordingAuditWriter:
    _clean_pos_tables()
    writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.shared.audit.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.service.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.sync_service.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setenv("POS_PROVIDER_MODE", "stub")
    yield writer
    _clean_pos_tables()


def _seed_connection(
    tenant_id: UUID,
    membership_id: UUID,
    *,
    connection_id: UUID | None = None,
    status: str = "active",
    last_synced_at: datetime | None = None,
    disconnected_at: datetime | None = None,
) -> UUID:
    cid = connection_id or uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into pos_connection (
                    id, tenant_id, provider, external_account_id, external_account_name,
                    access_token, refresh_token, status, connected_by,
                    connected_at, last_synced_at, disconnected_at
                ) values (
                    %s, %s, 'square', 'stub-merchant-12345', 'Demo POS Store',
                    'test-access-token', 'test-refresh-token', %s, %s,
                    now(), %s, %s
                )
                """,
                (cid, tenant_id, status, membership_id, last_synced_at, disconnected_at),
            )
        conn.commit()
    return cid


def test_overlapping_locks_prevent_concurrent_syncs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrency proof (T026):

    Proves overlapping advisory locks prevent concurrent syncs without any sleep-based race.
    """
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("pos-worker-concur") as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            last_synced_at=None,
        )

        holder_conn = psycopg.connect(TEST_DATABASE_URL or "", autocommit=True)
        try:
            # Hold the advisory lock on connection_id in an independent database session
            with holder_conn.cursor() as cur:
                cur.execute(
                    "select pg_try_advisory_lock(hashtext(%s))",
                    (str(conn_id),),
                )
                assert cur.fetchone()[0] is True

            # tick() selects the connection, but SyncService.sync() cannot acquire lock.
            # Worker catches ConflictError, skips with info log, does not fail.
            stats = tick(settings)
            assert stats["checked"] == 1
            assert stats["synced"] == 0
            assert stats["skipped_conflict"] == 1
            assert stats["failed"] == 0

        finally:
            with holder_conn.cursor() as cur:
                cur.execute(
                    "select pg_advisory_unlock(hashtext(%s))",
                    (str(conn_id),),
                )
            holder_conn.close()

        # Second tick(): lock is free, sync completes successfully
        stats2 = tick(settings)
        assert stats2["checked"] == 1
        assert stats2["synced"] == 1
        assert stats2["skipped_conflict"] == 0
        assert stats2["failed"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select last_synced_at from pos_connection where id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
        assert row is not None
        assert row["last_synced_at"] is not None


def test_tick_picks_up_due_connections_and_skips_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tick() picks up null or >1-day last_synced_at, skips recent (<1 day) and non-active."""
    settings = settings_for_test_db(monkeypatch)
    with (
        committed_smart_context("pos-worker-g1") as ctx1,
        committed_smart_context("pos-worker-g2") as ctx2,
        committed_smart_context("pos-worker-g3") as ctx3,
        committed_smart_context("pos-worker-g4") as ctx4,
    ):
        # Conn 1: active, last_synced_at is null -> DUE
        conn1 = _seed_connection(
            ctx1.workspace.tenant_id,
            ctx1.workspace.membership_id,
            last_synced_at=None,
        )

        # Conn 2: active, last_synced_at is 2 days ago -> DUE
        two_days_ago = datetime.now(UTC) - timedelta(days=2)
        conn2 = _seed_connection(
            ctx2.workspace.tenant_id,
            ctx2.workspace.membership_id,
            last_synced_at=two_days_ago,
        )

        # Conn 3: active, last_synced_at is 1 hour ago -> NOT DUE (skip)
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        conn3 = _seed_connection(
            ctx3.workspace.tenant_id,
            ctx3.workspace.membership_id,
            last_synced_at=one_hour_ago,
        )

        # Conn 4: disconnected -> NOT ACTIVE (skip)
        _seed_connection(
            ctx4.workspace.tenant_id,
            ctx4.workspace.membership_id,
            status="disconnected",
            last_synced_at=None,
            disconnected_at=datetime.now(UTC),
        )

        stats = tick(settings)
        # Exactly conn1 and conn2 must be picked up and synced
        assert stats["checked"] == 2
        assert stats["synced"] == 2
        assert stats["failed"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select id, last_synced_at
                    from pos_connection
                    where id in (%s, %s, %s)
                    """,
                    (conn1, conn2, conn3),
                )
                rows = {r["id"]: r["last_synced_at"] for r in cur.fetchall()}

        assert rows[conn1] is not None
        assert rows[conn1] > two_days_ago
        assert rows[conn2] is not None
        assert rows[conn2] > two_days_ago
        # conn3 was skipped, its last_synced_at was not touched
        assert abs((rows[conn3] - one_hour_ago).total_seconds()) < 5


def test_tick_continues_past_failure_to_process_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resilience: one connection failing does not stop subsequent connections from syncing."""
    settings = settings_for_test_db(monkeypatch)
    with (
        committed_smart_context("pos-worker-res-1") as ctx1,
        committed_smart_context("pos-worker-res-2") as ctx2,
    ):
        conn_a = _seed_connection(
            ctx1.workspace.tenant_id,
            ctx1.workspace.membership_id,
            last_synced_at=None,
        )
        # Only its side effect (a second connection due for sync) matters here.
        _seed_connection(
            ctx2.workspace.tenant_id,
            ctx2.workspace.membership_id,
            last_synced_at=None,
        )

        orig_sync = SyncService.sync

        def _flaky_sync(self: SyncService, *args: object, **kwargs: object) -> dict[str, object]:
            # Fail for conn_a only
            c_id = kwargs.get("connection_id")
            if c_id == conn_a:
                raise RuntimeError("Boom for connection A")
            return orig_sync(self, *args, **kwargs)

        monkeypatch.setattr(SyncService, "sync", _flaky_sync)

        stats = tick(settings)
        assert stats["checked"] == 2
        assert stats["synced"] == 1
        assert stats["failed"] == 1


def test_run_loop_once_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worker loop with once=True terminates cleanly without hanging."""
    settings = settings_for_test_db(monkeypatch)
    run_loop(settings, once=True)
