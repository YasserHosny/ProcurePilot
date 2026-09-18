"""Integration tests for accounting synchronization (R3.1, US2, task T023).

Covers:
- Full sync via StubConnector creates expected synced_bill and synced_vendor rows
  (Acceptance Scenario 2.1)
- Re-sync with updated bill reflected in ProcurePilot (Acceptance Scenario 2.4)
- 90-day initial sync window is respected (FR-015)
- Two concurrent sync triggers for the same connection — one succeeds, one gets 409/ConflictError
- A needs_reauth connection's sync attempt fails gracefully without crashing or partial writes
- TokenRefreshFailedError transitions connection to needs_reauth and maps to 404 in router
- Router RBAC on POST /accounting/sync (owner/buyer allowed, others 403)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import ConflictError
from procurepilot_api.main import create_app
from procurepilot_api.modules.accounting.connector import (
    OAuthTokens,
    RawBill,
    StubConnector,
)
from procurepilot_api.modules.accounting.quickbooks_client import QuickBooksAuthError
from procurepilot_api.modules.accounting.sync_service import (
    ConnectionNotActiveError,
    SyncService,
    TokenRefreshFailedError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        self.events.append(event)


@pytest.fixture(autouse=True)
def _mock_audit_writer(monkeypatch: pytest.MonkeyPatch) -> RecordingAuditWriter:
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
    return writer


def _app(
    monkeypatch: pytest.MonkeyPatch,
    member: object,
    audit_writer: RecordingAuditWriter | None = None,
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("ACCOUNTING_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    writer = audit_writer or RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_audit_writer",
        lambda: writer,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.sync_service.get_audit_writer",
        lambda: writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, writer


def _seed_connection(
    tenant_id: UUID,
    membership_id: UUID,
    *,
    connection_id: UUID | None = None,
    status: str = "active",
    last_synced_at: datetime | None = None,
    disconnected_at: datetime | None = None,
    realm_id: str = "stub-realm-12345",
    display_name: str = "ProcurePilot Demo Company",
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
                    %s, %s, 'quickbooks', %s, %s,
                    'test-access-token', 'test-refresh-token', %s, %s,
                    now(), %s, %s
                )
                """,
                (
                    cid,
                    tenant_id,
                    realm_id,
                    display_name,
                    status,
                    membership_id,
                    last_synced_at,
                    disconnected_at,
                ),
            )
        conn.commit()
    return cid


def test_full_sync_creates_synced_vendors_and_bills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 2.1: Full sync populates synced_vendor and synced_bill."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-full", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        service = SyncService()
        result = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )

        assert result["status"] == "completed"
        assert result["vendors_synced"] == 3
        assert result["bills_synced"] == 3

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select provider_vendor_id, display_name
                    from synced_vendor
                    where tenant_id = %s and connection_id = %s
                    order by provider_vendor_id
                    """,
                    (context.workspace.tenant_id, conn_id),
                )
                vendors = cur.fetchall()

                cur.execute(
                    """
                    select provider_bill_id, amount, currency, bill_date, provider_status
                    from synced_bill
                    where tenant_id = %s and connection_id = %s
                    order by provider_bill_id
                    """,
                    (context.workspace.tenant_id, conn_id),
                )
                bills = cur.fetchall()

                cur.execute(
                    "select last_synced_at from accounting_connection where id = %s",
                    (conn_id,),
                )
                conn_row = cur.fetchone()

        assert len(vendors) == 3
        assert vendors[0]["provider_vendor_id"] == "stub-vendor-001"
        assert vendors[0]["display_name"] == "Global Office Supplies"

        assert len(bills) == 3
        assert bills[0]["provider_bill_id"] == "stub-bill-101"
        assert bills[0]["amount"] == Decimal("1250.0000")
        assert bills[0]["currency"] == "USD"
        assert bills[0]["provider_status"] == "open"

        assert conn_row is not None
        assert conn_row["last_synced_at"] is not None


def test_resync_reflects_updated_bill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 2.4: Changes at provider reflect upon re-sync."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-update", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        today = date.today()
        initial_bills = [
            RawBill(
                provider_bill_id="stub-bill-101",
                provider_vendor_id="stub-vendor-001",
                amount=Decimal("1250.00"),
                currency="USD",
                bill_date=today - timedelta(days=15),
                status="open",
            ),
        ]
        initial_connector = StubConnector(bills=initial_bills)

        service = SyncService(connector=initial_connector)
        service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )

        # Provider updates bill amount to 1500.50 and status to paid
        updated_bills = [
            RawBill(
                provider_bill_id="stub-bill-101",
                provider_vendor_id="stub-vendor-001",
                amount=Decimal("1500.50"),
                currency="USD",
                bill_date=today - timedelta(days=15),
                status="paid",
            ),
        ]
        updated_connector = StubConnector(bills=updated_bills)

        service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
            connector=updated_connector,
        )

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select amount, provider_status, updated_at
                    from synced_bill
                    where tenant_id = %s and provider_bill_id = 'stub-bill-101'
                    """,
                    (context.workspace.tenant_id,),
                )
                bill = cur.fetchone()

        assert bill is not None
        assert bill["amount"] == Decimal("1500.5000")
        assert bill["provider_status"] == "paid"


def test_initial_sync_respects_90_day_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-015: First sync scopes to bills from last 90 days; subsequent sync is unbounded."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-90day", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            last_synced_at=None,
        )

        today = date.today()
        bills = [
            RawBill(
                provider_bill_id="bill-recent-80d",
                provider_vendor_id="stub-vendor-001",
                amount=Decimal("100.00"),
                currency="USD",
                bill_date=today - timedelta(days=80),
                status="open",
            ),
            RawBill(
                provider_bill_id="bill-old-100d",
                provider_vendor_id="stub-vendor-001",
                amount=Decimal("200.00"),
                currency="USD",
                bill_date=today - timedelta(days=100),
                status="open",
            ),
        ]
        connector = StubConnector(bills=bills)
        service = SyncService(connector=connector)

        # First sync: last_synced_at is null -> since is connected_at - 90 days (~90 days ago)
        res1 = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )
        assert res1["bills_synced"] == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select provider_bill_id from synced_bill where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                synced_ids = {r["provider_bill_id"] for r in cur.fetchall()}

        assert "bill-recent-80d" in synced_ids
        assert "bill-old-100d" not in synced_ids

        # Subsequent sync: last_synced_at is now set -> unbounded (since=1970-01-01)
        res2 = service.sync(
            settings,
            tenant_id=context.workspace.tenant_id,
            connection_id=conn_id,
        )
        assert res2["bills_synced"] == 2


def test_concurrent_sync_triggers_prevented_by_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: Two concurrent sync triggers for the same connection — one wins, one gets 409."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-concurrency", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
        )

        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Hold the advisory lock in a separate dedicated connection
        lock_conn = psycopg.connect(TEST_DATABASE_URL or "", autocommit=True)
        try:
            with lock_conn.cursor() as cur:
                cur.execute(
                    "select pg_try_advisory_lock(hashtext(%s))",
                    (str(conn_id),),
                )
                assert cur.fetchone()[0] is True

            # 1. Direct SyncService.sync call raises ConflictError
            service = SyncService()
            with pytest.raises(ConflictError):
                service.sync(
                    settings,
                    tenant_id=context.workspace.tenant_id,
                    connection_id=conn_id,
                )

            # 2. HTTP POST /accounting/sync returns 409 Conflict
            res = client.post("/api/v1/accounting/sync")
            assert res.status_code == 409, res.text

        finally:
            # Release the lock
            with lock_conn.cursor() as cur:
                cur.execute(
                    "select pg_advisory_unlock(hashtext(%s))",
                    (str(conn_id),),
                )
            lock_conn.close()

        # Once lock is released, HTTP sync succeeds with 202
        res2 = client.post("/api/v1/accounting/sync")
        assert res2.status_code == 202, res2.text
        assert res2.json() == {"status": "enqueued"}


def test_needs_reauth_connection_sync_fails_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec Acceptance Scenario 1.4: Connection in needs_reauth fails gracefully."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-reauth", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            status="needs_reauth",
        )

        # Direct service call raises ConnectionNotActiveError
        service = SyncService()
        with pytest.raises(ConnectionNotActiveError) as exc_info:
            service.sync(
                settings,
                tenant_id=context.workspace.tenant_id,
                connection_id=conn_id,
            )
        assert exc_info.value.status == "needs_reauth"

        # HTTP trigger translates to 404 (no active connection)
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.post("/api/v1/accounting/sync")
        assert res.status_code == 404, res.text

        # Verify no partial writes to synced_bill
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select count(*) from synced_bill where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0


def test_token_refresh_failed_transitions_to_needs_reauth_and_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 1.4: Failed token refresh marks needs_reauth and maps to 404."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("acct-sync-token-fail", supplier_count=1) as context:
        conn_id = _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            status="active",
        )

        class FailingRefreshConnector(StubConnector):
            def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
                raise QuickBooksAuthError("invalid_grant: token revoked")

        service = SyncService(connector=FailingRefreshConnector())

        with pytest.raises(TokenRefreshFailedError):
            service.sync(
                settings,
                tenant_id=context.workspace.tenant_id,
                connection_id=conn_id,
            )

        # Connection status must now be 'needs_reauth' in database
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select status from accounting_connection where id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
        assert row is not None
        assert row["status"] == "needs_reauth"

        # Calling HTTP POST /accounting/sync now returns 404
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/api/v1/accounting/sync")
        assert res.status_code == 404, res.text


def test_router_sync_rbac_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T022: Role gates for POST /accounting/sync — owner/buyer allowed, viewer 403."""
    with committed_smart_context("acct-sync-rbac", supplier_count=1) as context:
        _seed_connection(
            context.workspace.tenant_id,
            context.workspace.membership_id,
            status="active",
        )

        # Viewer gets 403
        viewer = member_from_workspace(context.workspace, role=MemberRole.viewer)
        viewer_app, _ = _app(monkeypatch, viewer)
        viewer_client = TestClient(viewer_app, raise_server_exceptions=False)
        res_viewer = viewer_client.post("/api/v1/accounting/sync")
        assert res_viewer.status_code == 403, res_viewer.text

        # Buyer gets 202
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        buyer_app, _ = _app(monkeypatch, buyer)
        buyer_client = TestClient(buyer_app, raise_server_exceptions=False)
        res_buyer = buyer_client.post("/api/v1/accounting/sync")
        assert res_buyer.status_code == 202, res_buyer.text
        assert res_buyer.json() == {"status": "enqueued"}

        # Bills list endpoint accessible to any member (including viewer)
        bills_res = viewer_client.get("/api/v1/accounting/bills")
        assert bills_res.status_code == 200, bills_res.text
        data = bills_res.json()
        assert "items" in data
        assert len(data["items"]) == 3
