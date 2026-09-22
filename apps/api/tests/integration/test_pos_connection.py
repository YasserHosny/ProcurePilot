"""Integration tests for POS and inventory connection lifecycle (R3.2, tasks T010-T013).

Covers:
- owner can start a connection and complete it via the callback (stub flow) — ends active
- non-owner (buyer) gets 403 on POST /pos/connect and POST /pos/disconnect
- a second connect attempt while one is active returns 409
- disconnect preserves the row (disconnected_at set, row still exists, not deleted)
  and previously-synced data stays queryable (Acceptance Scenario 1.2)
- a callback with error present, or missing code, leaves no connection row at all (Scenario 1.3)
- a connection whose token refresh fails transitions to needs_reauth on the next sync attempt
  (Scenario 1.4)
- GET /pos/connection returns 404 when no connection has ever existed for the tenant
- cross-tenant: a connection for tenant A resolves not-found (404, never 403) for tenant B
- reconnecting after a disconnect creates a genuinely distinct new pos_connection row
  (both old and new rows independently queryable, preserving audit trail)
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import UUID

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
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.pos.connector import OAuthTokens, StubConnector
from procurepilot_api.modules.pos.service import ConnectionService
from procurepilot_api.modules.pos.square_client import SquareAuthError
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
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, audit_writer


def test_get_before_any_connection_exists_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-missing") as context:
        member = member_from_workspace(context.workspace)
        app, _ = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/api/v1/pos/connection")
        assert res.status_code == 404, res.text


def test_non_owner_cannot_start_connection_or_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-rbac") as context:
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        app, _ = _app(monkeypatch, buyer)
        client = TestClient(app, raise_server_exceptions=False)

        res_connect = client.post("/api/v1/pos/connect")
        assert res_connect.status_code == 403, res_connect.text

        res_disc = client.post("/api/v1/pos/disconnect")
        assert res_disc.status_code == 403, res_disc.text


def test_owner_can_start_and_complete_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-flow") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/pos/connect")
        assert start_res.status_code == 200, start_res.text
        auth_url = start_res.json()["authorization_url"]
        assert "connect.squareup.com" in auth_url or "square" in auth_url.lower()

        parsed = urlparse(auth_url)
        qs = parse_qs(parsed.query)
        assert "state" in qs
        state = qs["state"][0]

        cb_res = client.get(
            f"/api/v1/pos/connect/callback?code=stub-auth-code&state={state}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302, cb_res.text
        location = cb_res.headers["location"]
        assert "/pos" in location
        assert "pos_connected=success" in location

        conn_res = client.get("/api/v1/pos/connection")
        assert conn_res.status_code == 200, conn_res.text
        conn_data = conn_res.json()
        assert conn_data["status"] == "active"
        assert conn_data["provider"] == "square"
        assert conn_data["display_name"] == "ProcurePilot Demo POS Store"
        assert conn_data["connected_at"] is not None
        assert conn_data["disconnected_at"] is None

        created_events = [
            e for e in audit_writer.events if e.action == "pos.connection_created"
        ]
        assert len(created_events) == 1
        assert created_events[0].tenant_id == context.workspace.tenant_id

        # Any member (e.g. buyer) of the same workspace can read connection status
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        buyer_app, _ = _app(monkeypatch, buyer)
        buyer_client = TestClient(buyer_app, raise_server_exceptions=False)
        buyer_res = buyer_client.get("/api/v1/pos/connection")
        assert buyer_res.status_code == 200, buyer_res.text
        assert buyer_res.json()["id"] == conn_data["id"]


def test_second_connect_attempt_while_active_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-conflict") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/pos/connect")
        assert start_res.status_code == 200, start_res.text
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]

        client.get(
            f"/api/v1/pos/connect/callback?code=code-1&state={state}",
            follow_redirects=False,
        )

        second_res = client.post("/api/v1/pos/connect")
        assert second_res.status_code == 409, second_res.text


def test_disconnect_preserves_row_and_updates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-disc") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/pos/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/pos/connect/callback?code=code-1&state={state}",
            follow_redirects=False,
        )

        disc_res = client.post("/api/v1/pos/disconnect")
        assert disc_res.status_code == 200, disc_res.text
        disc_data = disc_res.json()
        assert disc_data["status"] == "disconnected"
        assert disc_data["disconnected_at"] is not None

        get_res = client.get("/api/v1/pos/connection")
        assert get_res.status_code == 200, get_res.text
        assert get_res.json()["status"] == "disconnected"

        # Verify DB directly: row is preserved (not deleted)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select count(*), status from pos_connection
                    where tenant_id = %s group by status
                    """,
                    (context.workspace.tenant_id,),
                )
                rows = cur.fetchall()
                assert len(rows) == 1
                count, db_status = rows[0]
                assert count == 1
                assert db_status == "disconnected"

        disc_events = [
            e for e in audit_writer.events if e.action == "pos.connection_disconnected"
        ]
        assert len(disc_events) == 1
        assert disc_events[0].tenant_id == context.workspace.tenant_id

        # Disconnecting again when already disconnected returns 404
        second_disc = client.post("/api/v1/pos/disconnect")
        assert second_disc.status_code == 404, second_disc.text


def test_callback_with_error_or_missing_code_leaves_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("pos-conn-decline") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/pos/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]

        # Case 1: error parameter from consent denial
        err_res = client.get(
            f"/api/v1/pos/connect/callback?error=access_denied&state={state}",
            follow_redirects=False,
        )
        assert err_res.status_code == 302, err_res.text
        assert "pos_connected=failed" in err_res.headers["location"]

        get_res = client.get("/api/v1/pos/connection")
        assert get_res.status_code == 404, get_res.text

        # Case 2: missing code
        nocode_res = client.get(
            f"/api/v1/pos/connect/callback?state={state}",
            follow_redirects=False,
        )
        assert nocode_res.status_code == 302, nocode_res.text
        assert "pos_connected=failed" in nocode_res.headers["location"]

        # Confirm DB has 0 rows for this tenant
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from pos_connection where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0


def test_cross_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        committed_smart_context("pos-t-a") as ctx_a,
        committed_smart_context("pos-t-b") as ctx_b,
    ):
        owner_a = member_from_workspace(ctx_a.workspace, role=MemberRole.owner)
        owner_b = member_from_workspace(ctx_b.workspace, role=MemberRole.owner)

        app_a, _ = _app(monkeypatch, owner_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)

        start_res = client_a.post("/api/v1/pos/connect")
        state_a = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client_a.get(
            f"/api/v1/pos/connect/callback?code=code-a&state={state_a}",
            follow_redirects=False,
        )

        # Confirm tenant A has an active connection
        assert client_a.get("/api/v1/pos/connection").status_code == 200

        # Tenant B member querying POS connection gets 404 (never 403, never tenant A data)
        app_b, _ = _app(monkeypatch, owner_b)
        client_b = TestClient(app_b, raise_server_exceptions=False)

        res_b = client_b.get("/api/v1/pos/connection")
        assert res_b.status_code == 404, res_b.text

        # Tenant B owner cannot disconnect Tenant A's connection
        disc_b = client_b.post("/api/v1/pos/disconnect")
        assert disc_b.status_code == 404, disc_b.text


def test_reconnect_after_disconnect_creates_new_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reconnect after disconnect creates a genuinely distinct new pos_connection row."""
    with committed_smart_context("pos-reconnect") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # 1. Connect
        start_res_1 = client.post("/api/v1/pos/connect")
        state_1 = parse_qs(urlparse(start_res_1.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/pos/connect/callback?code=code-1&state={state_1}",
            follow_redirects=False,
        )
        conn_1 = client.get("/api/v1/pos/connection").json()
        assert conn_1["status"] == "active"
        conn_1_id = conn_1["id"]

        # 2. Disconnect
        disc_res = client.post("/api/v1/pos/disconnect")
        assert disc_res.status_code == 200
        assert disc_res.json()["status"] == "disconnected"

        # 3. Reconnect
        start_res_2 = client.post("/api/v1/pos/connect")
        assert start_res_2.status_code == 200
        state_2 = parse_qs(urlparse(start_res_2.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/pos/connect/callback?code=code-2&state={state_2}",
            follow_redirects=False,
        )
        conn_2 = client.get("/api/v1/pos/connection").json()
        assert conn_2["status"] == "active"
        conn_2_id = conn_2["id"]

        # IDs must be genuinely distinct (old row never reactivated)
        assert conn_1_id != conn_2_id

        # Verify DB directly: both rows exist and are independently queryable
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, status, disconnected_at
                    from pos_connection
                    where tenant_id = %s
                    order by created_at asc
                    """,
                    (context.workspace.tenant_id,),
                )
                rows = cur.fetchall()
                assert len(rows) == 2
                assert str(rows[0]["id"]) == conn_1_id
                assert rows[0]["status"] == "disconnected"
                assert rows[0]["disconnected_at"] is not None

                assert str(rows[1]["id"]) == conn_2_id
                assert rows[1]["status"] == "active"
                assert rows[1]["disconnected_at"] is None


def test_token_refresh_failed_transitions_to_needs_reauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 1.4: Connection whose token refresh fails transitions to needs_reauth."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("pos-token-fail") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Connect
        start_res = client.post("/api/v1/pos/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/pos/connect/callback?code=code-1&state={state}",
            follow_redirects=False,
        )
        conn_data = client.get("/api/v1/pos/connection").json()
        conn_id = UUID(conn_data["id"])

        class FailingRefreshConnector(StubConnector):
            def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
                raise SquareAuthError("invalid_grant: token revoked")

        service = ConnectionService(settings=settings)

        with pytest.raises(SquareAuthError):
            service.refresh_connection_tokens(
                tenant_id=context.workspace.tenant_id,
                connection_id=conn_id,
                connector=FailingRefreshConnector(),
            )

        # Connection status in DB must now be 'needs_reauth'
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "select status from pos_connection where id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
        assert row is not None
        assert row["status"] == "needs_reauth"

        # GET /pos/connection reflects needs_reauth
        status_res = client.get("/api/v1/pos/connection")
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "needs_reauth"


def test_disconnected_connection_preserves_synced_product_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 1.2: Previously-synced data stays queryable after disconnect."""
    with committed_smart_context("pos-disc-signals") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        # Connect
        start_res = client.post("/api/v1/pos/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/pos/connect/callback?code=code-1&state={state}",
            follow_redirects=False,
        )
        conn_data = client.get("/api/v1/pos/connection").json()
        conn_id = conn_data["id"]

        # Seed a synced_product_signal row linked to this connection
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    insert into synced_product_signal (
                        tenant_id,
                        pos_connection_id,
                        external_item_id,
                        external_item_name,
                        stock_on_hand,
                        sales_velocity_per_day,
                        velocity_window_days
                    ) values (
                        %s, %s, 'stub-item-001', 'Organic Whole Milk 1 Gallon',
                        45.0, 4.5, 30
                    )
                    """,
                    (context.workspace.tenant_id, conn_id),
                )
            db_conn.commit()

        # Disconnect
        disc_res = client.post("/api/v1/pos/disconnect")
        assert disc_res.status_code == 200
        assert disc_res.json()["status"] == "disconnected"

        # Verify synced_product_signal is still present and queryable
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as db_conn:
            with db_conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    select external_item_id, external_item_name,
                           stock_on_hand, sales_velocity_per_day
                    from synced_product_signal
                    where tenant_id = %s and pos_connection_id = %s
                    """,
                    (context.workspace.tenant_id, conn_id),
                )
                signal_row = cur.fetchone()

        assert signal_row is not None
        assert signal_row["external_item_id"] == "stub-item-001"
        assert signal_row["external_item_name"] == "Organic Whole Milk 1 Gallon"
