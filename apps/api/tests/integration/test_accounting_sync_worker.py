"""Integration tests for the daily accounting sync worker (R3.1, US2, task T025).

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
from procurepilot_api.modules.accounting.sync_service import SyncService
from procurepilot_api.shared.audit import AuditEventCreate
from procurepilot_api.workers.accounting_sync_worker import run_loop, tick

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


def _clean_accounting_tables() -> None:
    if TEST_DATABASE_URL:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # reconciliation_discrepancy FKs into synced_bill/purchase_record — must be
                # cleared first, or synced_bill's own delete below hits a FK violation now that
                # SyncService.sync() (via ReconciliationService.recompute_discrepancies) creates
                # rows here on every sync this test suite runs.
                cur.execute("delete from reconciliation_discrepancy")
                cur.execute("delete from purchase_bill_match")
                cur.execute("delete from synced_bill")
                cur.execute("delete from synced_vendor")
                cur.execute("delete from accounting_connection")
            conn.commit()


@pytest.fixture(autouse=True)
def _mock_audit_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> RecordingAuditWriter:
    _clean_accounting_tables()
    writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.shared.audit.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.get_audit_writer",
        lambda: writer,
    )
    yield writer
    _clean_accounting_tables()


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
                insert into accounting_connection (
                    id, tenant_id, provider, realm_id, display_name,
                    access_token, refresh_token, status, connected_by,
                    connected_at, last_synced_at, disconnected_at
                ) values (
                    %s, %s, 'quickbooks', 'stub-realm-12345', 'Demo Company',
                    'test-access-token', 'test-refresh-token', %s, %s,
                    now(), %s, %s
                )
                """,
                (
                    cid,
                    tenant_id,
                    status,
                    membership_id,
                    last_synced_at,
                    disconnected_at,
                ),
            )
        conn.commit()
    return cid


def test_concurrency_advisory_lock_prevents_duplicate_syncs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Modeled on test_concurrency_skip_locked_prevents_duplicate_claims.

    Proves overlapping advisory locks prevent concurrent syncs without any sleep-based race.
    """
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-worker-concur", supplier_count=1) as context:
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

            # tick() selects the connection, but SyncService.sync() cannot acquire the lock.
            # Worker catches ConflictError, skips with info log, does not fail.
            stats = tick(settings)
            assert stats["checked"] == 1
            assert stats["synced"] == 0
            assert stats["skipped_conflict"] == 1
            assert stats["failed"] == 0

        finally:
            # Release lock in holder connection
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
                    "select last_synced_at from accounting_connection where id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
        assert row is not None
        assert row["last_synced_at"] is not None


def test_tick_picks_up_due_connections_and_skips_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tick() picks up null or >1-day last_synced_at, skips recent and non-active."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-worker-gating-1") as ctx1:
        with committed_smart_context("acct-worker-gating-2") as ctx2:
            with committed_smart_context("acct-worker-gating-3") as ctx3:
                with committed_smart_context("acct-worker-gating-4") as ctx4:
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
                                from accounting_connection
                                where id in (%s, %s, %s)
                                """,
                                (conn1, conn2, conn3),
                            )
                            rows = {r["id"]: r["last_synced_at"] for r in cur.fetchall()}

                    assert rows[conn1] is not None
                    assert rows[conn1] > two_days_ago
                    assert rows[conn2] is not None
                    assert rows[conn2] > two_days_ago
                    # conn3 last_synced_at was not modified by the worker
                    assert abs((rows[conn3] - one_hour_ago).total_seconds()) < 5


def test_tick_continues_past_failure_to_process_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed 3 connections: one fails, two succeed; assert both successes happen despite failure."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-worker-resil-1") as ctx1:
        with committed_smart_context("acct-worker-resil-2") as ctx2:
            with committed_smart_context("acct-worker-resil-3") as ctx3:
                conn_a = _seed_connection(
                    ctx1.workspace.tenant_id,
                    ctx1.workspace.membership_id,
                    last_synced_at=None,
                )
                conn_b = _seed_connection(
                    ctx2.workspace.tenant_id,
                    ctx2.workspace.membership_id,
                    last_synced_at=None,
                )
                conn_c = _seed_connection(
                    ctx3.workspace.tenant_id,
                    ctx3.workspace.membership_id,
                    last_synced_at=None,
                )

                # Custom SyncService that fails exclusively for conn_b
                class FaultySyncService(SyncService):
                    def sync(
                        self,
                        settings_arg: object,
                        *,
                        tenant_id: UUID,
                        connection_id: UUID,
                        connector: object = None,
                    ) -> dict[str, object]:
                        if connection_id == conn_b:
                            raise RuntimeError("Simulated remote QuickBooks network error")
                        return super().sync(
                            settings_arg,  # type: ignore[arg-type]
                            tenant_id=tenant_id,
                            connection_id=connection_id,
                            connector=connector,  # type: ignore[arg-type]
                        )

                stats = tick(settings, sync_service=FaultySyncService())

                assert stats["checked"] == 3
                assert stats["synced"] == 2
                assert stats["failed"] == 1
                assert stats["skipped_conflict"] == 0

                with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
                    with conn.cursor() as cur:
                        cur.execute("set local role service_role")
                        cur.execute(
                            """
                            select id, last_synced_at
                            from accounting_connection
                            where id in (%s, %s, %s)
                            """,
                            (conn_a, conn_b, conn_c),
                        )
                        rows = {r["id"]: r["last_synced_at"] for r in cur.fetchall()}

                # Conn A and Conn C succeeded and have last_synced_at populated
                assert rows[conn_a] is not None
                assert rows[conn_c] is not None
                # Conn B failed and remains unsynced (last_synced_at is None)
                assert rows[conn_b] is None


def test_run_loop_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that run_loop with once=True completes a single iteration and exits."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-worker-loop") as context:
        _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            last_synced_at=None,
        )
        # Calling run_loop with once=True should execute tick() and return without hanging
        run_loop(settings, once=True, interval_seconds=1)
