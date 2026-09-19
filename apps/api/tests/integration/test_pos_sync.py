"""Integration tests for POS synchronization and usage signals (R3.2, tasks T022, T024, T025).

Covers:
- Acceptance Scenario 2.1: Full sync against StubConnector creates synced_product_signal
  rows with correct stock and velocity figures.
- Acceptance Scenario 2.2: An item with no inventory tracking (stub-item-003) shows null stock,
  never a fabricated zero.
- Acceptance Scenario 2.3: Stale stock figure's stock_synced_at reflects real staleness.
- FR-013: An item with fewer than 30 days of transaction history (stub-item-005) gets
  velocity_window_days_observed set below velocity_window_days (provisional figure).
- Concurrency: Two concurrent sync triggers for the same connection — one wins, one gets 409.
- Graceful failure: A needs_reauth connection's sync attempt fails gracefully (404, no crash).
- Audit trail: pos.sync_started audit event is recorded even when sync raises immediately
  after lock acquisition.
- T025 Reconnect-dedup regression: Connect, sync, disconnect, reconnect (new pos_connection row),
  sync again:
  (a) no duplicate synced_product_signal row exists for any external_item_id seen before disconnect
  (b) each such row's pos_connection_id now points at the new connection
  (c) the pos_product_match row created before disconnect is untouched (same id, no re-matching).
- T024 SC-002 aggregate coverage: Seed >=90% matchable fixture items, run sync, assert >=90%
  top-selling items show computed sales_velocity_per_day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    make_workspace_product,
)
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.pos.connector import (
    RawInventoryLevel,
    RawSalesTransaction,
    StubConnector,
)
from procurepilot_api.modules.pos.sync_service import SyncService
from procurepilot_api.shared.audit import AuditEventCreate
from procurepilot_api.shared.rate_limit import mutation_limiter

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


@pytest.fixture(autouse=True)
def _reset_mutation_limiter() -> None:
    # The TestClient sends no real bearer header, so tenant_member_rate_limit_key falls back to
    # get_remote_address ("testclient") for every test in this file — without a reset, repeated
    # /pos/sync calls across unrelated test functions would share one bucket and spuriously 429
    # (this codebase's own established pattern, see test_mutation_rate_limits.py).
    mutation_limiter.reset()


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


def _app(
    monkeypatch: pytest.MonkeyPatch, member: object
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("POS_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    audit_writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.service.get_audit_writer",
        lambda: audit_writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.sync_service.get_audit_writer",
        lambda: audit_writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, audit_writer


def _connect_owner(client: TestClient) -> dict[str, object]:
    """Helper to complete the OAuth stub flow and return active connection data."""
    start_res = client.post("/api/v1/pos/connect")
    assert start_res.status_code == 200, start_res.text
    auth_url = start_res.json()["authorization_url"]
    state = parse_qs(urlparse(auth_url).query)["state"][0]

    cb_res = client.get(
        f"/api/v1/pos/connect/callback?code=stub-auth-code&state={state}",
        follow_redirects=False,
    )
    assert cb_res.status_code == 302, cb_res.text

    conn_res = client.get("/api/v1/pos/connection")
    assert conn_res.status_code == 200, conn_res.text
    return conn_res.json()


def test_full_sync_creates_signals_with_correct_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 2.1 & 2.2: Full sync creates signals with stock and velocity figures."""
    with committed_smart_context("pos-sync-full") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        _connect_owner(client)

        # Trigger manual sync
        sync_res = client.post("/api/v1/pos/sync")
        assert sync_res.status_code == 202, sync_res.text
        assert sync_res.json()["status"] == "enqueued"

        # Query synced signals
        sig_res = client.get("/api/v1/pos/signals")
        assert sig_res.status_code == 200, sig_res.text
        signals = {s["external_item_name"]: s for s in sig_res.json()["items"]}

        # 1. stub-item-001 has stock and 30-day velocity
        milk = signals.get("Organic Whole Milk 1 Gallon")
        assert milk is not None
        assert milk["stock_on_hand"] == "45.0000"
        assert milk["sales_velocity_per_day"] == "0.8000"
        assert milk["velocity_window_days"] == 30

        # 2. stub-item-002 has stock but zero sales transactions
        blender = signals.get("Stainless Steel Immersion Blender")
        assert blender is not None
        assert blender["stock_on_hand"] == "12.0000"
        assert blender["sales_velocity_per_day"] is None

        # 3. Acceptance Scenario 2.2: stub-item-003 has sales but no inventory tracking
        #    (null stock, never 0)
        slicing = signals.get("Bakery Counter Custom Slicing Service")
        assert slicing is not None
        assert slicing["stock_on_hand"] is None
        assert slicing["sales_velocity_per_day"] is not None

        # 4. FR-013: stub-item-005 has fewer than 30 days of history -> provisional figure
        cold_brew = signals.get("Cold Brew Concentrate 1L Bottle")
        assert cold_brew is not None
        assert cold_brew["sales_velocity_per_day"] is not None
        assert cold_brew["velocity_window_days_observed"] is not None
        assert cold_brew["velocity_window_days_observed"] < cold_brew["velocity_window_days"]

        # Check DB directly for observed window
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select velocity_window_days_observed
                    from synced_product_signal
                    where tenant_id = %s and external_item_id = 'stub-item-005'
                    """,
                    (context.workspace.tenant_id,),
                )
                row = cur.fetchone()
                assert row is not None
                assert row["velocity_window_days_observed"] is not None
                assert row["velocity_window_days_observed"] < 30


def test_stale_stock_reflects_real_staleness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 2.3: A stock figure from an earlier sync reflects its real timestamp."""
    with committed_smart_context("pos-sync-stale") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        _connect_owner(client)
        client.post("/api/v1/pos/sync")

        # Manually backdate stock_synced_at by 2 days in database
        stale_time = datetime.now() - timedelta(days=2)
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    update synced_product_signal
                    set stock_synced_at = %s
                    where tenant_id = %s and external_item_id = 'stub-item-001'
                    """,
                    (stale_time, context.workspace.tenant_id),
                )
            db_conn.commit()

        # Fetch signals and assert staleness is preserved
        sig_res = client.get("/api/v1/pos/signals")
        signals = {s["external_item_name"]: s for s in sig_res.json()["items"]}
        milk = signals["Organic Whole Milk 1 Gallon"]
        assert milk["stock_synced_at"] is not None
        synced_at = datetime.fromisoformat(milk["stock_synced_at"])
        # Should be approximately 2 days old
        assert (datetime.now() - synced_at.replace(tzinfo=None)).total_seconds() > 86400


def test_concurrent_sync_triggers_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-002: Two concurrent sync triggers for the same connection — one wins, one gets 409."""
    with committed_smart_context("pos-sync-concur") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        conn_data = _connect_owner(client)
        conn_id = conn_data["id"]

        # Hold the advisory lock on connection_id on an independent dedicated connection
        holder_conn = psycopg.connect(TEST_DATABASE_URL or "", autocommit=True)
        try:
            with holder_conn.cursor() as cur:
                cur.execute("select pg_try_advisory_lock(hashtext(%s))", (str(conn_id),))
                assert cur.fetchone()[0] is True

            # Trigger sync: advisory lock cannot be acquired -> 409 Conflict
            res = client.post("/api/v1/pos/sync")
            assert res.status_code == 409, res.text
            assert res.json()["code"] == "conflict"

        finally:
            with holder_conn.cursor() as cur:
                cur.execute("select pg_advisory_unlock(hashtext(%s))", (str(conn_id),))
            holder_conn.close()

        # After releasing lock, sync succeeds
        res2 = client.post("/api/v1/pos/sync")
        assert res2.status_code == 202


def test_needs_reauth_connection_fails_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 1.4: Sync against a needs_reauth connection returns 404,
    without crashing."""
    with committed_smart_context("pos-sync-reauth") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        conn_data = _connect_owner(client)
        conn_id = conn_data["id"]

        # Set status to needs_reauth
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update pos_connection set status = 'needs_reauth' where id = %s",
                    (conn_id,),
                )
            db_conn.commit()

        # Sync trigger should fail gracefully with 404
        res = client.post("/api/v1/pos/sync")
        assert res.status_code == 404, res.text


def test_sync_started_audit_recorded_even_when_sync_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T016/T022: pos.sync_started is recorded immediately upon lock acquisition,
    even if sync raises."""
    with committed_smart_context("pos-sync-audit-started") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        conn_data = _connect_owner(client)
        conn_id = UUID(str(conn_data["id"]))

        # Patch _execute_sync to fail immediately after lock acquisition
        def _fail_execute(*args: object, **kwargs: object) -> None:
            raise RuntimeError("Forced post-lock failure")

        monkeypatch.setattr(
            "procurepilot_api.modules.pos.sync_service.SyncService._execute_sync",
            _fail_execute,
        )

        settings = settings_for_test_db(monkeypatch)
        sync_service = SyncService(settings=settings)

        with pytest.raises(RuntimeError, match="Forced post-lock failure"):
            sync_service.sync(
                settings,
                tenant_id=context.workspace.tenant_id,
                connection_id=conn_id,
            )

        # Assert pos.sync_started was recorded
        actions = [e.action for e in audit_writer.events]
        assert "pos.sync_started" in actions
        assert "pos.sync_failed" in actions


def test_reconnect_dedup_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T025 (SC-005): Reconnect-dedup design proof.

    Connect, sync (creates signals + match), disconnect, reconnect (new pos_connection row),
    sync again, and assert:
    (a) no duplicate synced_product_signal row exists for any external_item_id seen
        before disconnect
    (b) each such row's pos_connection_id now points at the new connection
    (c) the pos_product_match row created before disconnect is untouched (same id, no re-matching).
    """
    with committed_smart_context("pos-reconnect-dedup") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Seed a matching workspace product so stub-item-001 gets matched automatically
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                make_workspace_product(
                    cur,
                    context.workspace,
                    name="Organic Whole Milk 1 Gallon",
                )
            db_conn.commit()

        # 1. Connect (creates connection 1)
        conn_1 = _connect_owner(client)
        conn_1_id = UUID(str(conn_1["id"]))

        # 2. Sync (creates signals + automatic match for stub-item-001)
        client.post("/api/v1/pos/sync")

        # Read original signal and match from DB
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select id, pos_connection_id, external_item_id
                    from synced_product_signal
                    where tenant_id = %s and external_item_id = 'stub-item-001'
                    """,
                    (context.workspace.tenant_id,),
                )
                orig_signal = cur.fetchone()
                assert orig_signal is not None
                assert orig_signal["pos_connection_id"] == conn_1_id
                orig_signal_id = orig_signal["id"]

                cur.execute(
                    """
                    select id, synced_product_signal_id, workspace_product_id, matched_at
                    from pos_product_match
                    where tenant_id = %s and synced_product_signal_id = %s
                    """,
                    (context.workspace.tenant_id, orig_signal_id),
                )
                orig_match = cur.fetchone()
                assert orig_match is not None
                orig_match_id = orig_match["id"]

        # 3. Disconnect connection 1
        disc_res = client.post("/api/v1/pos/disconnect")
        assert disc_res.status_code == 200

        # 4. Reconnect (creates connection 2 — new pos_connection row)
        conn_2 = _connect_owner(client)
        conn_2_id = UUID(str(conn_2["id"]))
        assert conn_2_id != conn_1_id, "Reconnect must insert a new connection id"

        # 5. Sync again under connection 2
        sync2_res = client.post("/api/v1/pos/sync")
        assert sync2_res.status_code == 202

        # 6. Verify assertions (a), (b), and (c)
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                # (a) No duplicate signal: exactly one row for stub-item-001, same signal ID
                cur.execute(
                    """
                    select id, pos_connection_id, external_item_id
                    from synced_product_signal
                    where tenant_id = %s and external_item_id = 'stub-item-001'
                    """,
                    (context.workspace.tenant_id,),
                )
                signal_rows = cur.fetchall()
                assert len(signal_rows) == 1, "Duplicate signal row created on reconnect!"
                updated_signal = signal_rows[0]
                assert updated_signal["id"] == orig_signal_id, "Signal ID must remain stable"

                # (b) pos_connection_id now points at new connection 2
                assert updated_signal["pos_connection_id"] == conn_2_id

                # (c) pos_product_match row is untouched (same id, same matched_at)
                cur.execute(
                    """
                    select id, synced_product_signal_id, workspace_product_id, matched_at
                    from pos_product_match
                    where tenant_id = %s and synced_product_signal_id = %s
                    """,
                    (context.workspace.tenant_id, orig_signal_id),
                )
                match_rows = cur.fetchall()
                assert len(match_rows) == 1
                assert match_rows[0]["id"] == orig_match_id
                assert match_rows[0]["matched_at"] == orig_match["matched_at"]


def test_sc002_aggregate_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T024 (SC-002): Aggregate coverage proof.

    Seed a batch of fixture items where >=90% are matchable by name/brand,
    run full sync, and assert that the resulting proportion of items showing a
    computed sales_velocity_per_day meets the >=90% claim.
    """
    with committed_smart_context("pos-sc002-cov") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Seed 10 products: 9 with exact matching names to catalogue, 1 unmatchable
        today = date.today()
        fixture_txns = []
        fixture_inv = []

        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                for i in range(1, 11):
                    item_id = f"coverage-item-{i:03d}"
                    item_name = f"Coverage Tested Product {i}"
                    # Items 1..9 have matching catalogue products
                    if i <= 9:
                        make_workspace_product(cur, context.workspace, name=item_name)

                    # All 10 items have sales transactions
                    fixture_txns.append(
                        RawSalesTransaction(
                            transaction_id=f"cov-txn-{i}",
                            external_item_id=item_id,
                            item_name=item_name,
                            quantity=Decimal("10.0000"),
                            transaction_date=today - timedelta(days=10),
                        )
                    )
                    fixture_inv.append(
                        RawInventoryLevel(
                            external_item_id=item_id,
                            item_name=item_name,
                            stock_on_hand=Decimal("50.0000"),
                        )
                    )
            db_conn.commit()

        # Connect owner
        _connect_owner(client)

        # Override active connector with our 10-item fixture
        custom_connector = StubConnector(
            transactions=fixture_txns,
            inventory_levels=fixture_inv,
        )
        monkeypatch.setattr(
            "procurepilot_api.modules.pos.sync_service.get_pos_connector",
            lambda *a, **kw: custom_connector,
        )

        # Run sync
        sync_res = client.post("/api/v1/pos/sync")
        assert sync_res.status_code == 202

        # Check coverage of sales velocity: 10 of 10 items have transactions
        # -> 100% computed velocity
        sig_res = client.get("/api/v1/pos/signals?limit=100")
        assert sig_res.status_code == 200
        items = sig_res.json()["items"]
        cov_items = [it for it in items if "Coverage Tested Product" in it["external_item_name"]]
        assert len(cov_items) == 10

        with_velocity = [it for it in cov_items if it["sales_velocity_per_day"] is not None]
        matched_items = [it for it in cov_items if it["matched"] is True]

        # Proportion of items with velocity must be >= 90% (here 10/10 = 100%)
        assert len(with_velocity) / len(cov_items) >= 0.90
        # Confident match coverage must also be >= 90% (9/10 = 90%)
        assert len(matched_items) / len(cov_items) >= 0.90
