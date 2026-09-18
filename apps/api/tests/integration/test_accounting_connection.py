"""Integration tests for accounting connection lifecycle (R3.1, tasks T012-T015).

Covers:
- owner can start a connection and complete it via the callback (stub flow) — ends active
- non-owner gets 403 on POST /accounting/connect and POST /accounting/disconnect
- a second connect attempt while one is active returns 409
- disconnect preserves the row (status='disconnected', row still exists, not deleted)
- a callback with error present, or missing code, leaves no connection row at all (Scenario 1.3)
- GET /accounting/connection returns 404 when no connection has ever existed for the tenant
- cross-tenant: a connection for tenant A resolves not-found (404, never 403) for tenant B
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
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


def _app(
    monkeypatch: pytest.MonkeyPatch, member: object
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("ACCOUNTING_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    audit_writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.accounting.service.get_audit_writer",
        lambda: audit_writer,
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, audit_writer


def test_get_before_any_connection_exists_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-missing") as context:
        member = member_from_workspace(context.workspace)
        app, _ = _app(monkeypatch, member)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/api/v1/accounting/connection")
        assert res.status_code == 404, res.text


def test_non_owner_cannot_start_connection_or_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-rbac") as context:
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        app, _ = _app(monkeypatch, buyer)
        client = TestClient(app, raise_server_exceptions=False)

        res_connect = client.post("/api/v1/accounting/connect")
        assert res_connect.status_code == 403, res_connect.text

        res_disc = client.post("/api/v1/accounting/disconnect")
        assert res_disc.status_code == 403, res_disc.text


def test_owner_can_start_and_complete_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-flow") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/accounting/connect")
        assert start_res.status_code == 200, start_res.text
        auth_url = start_res.json()["authorization_url"]
        assert "appcenter.intuit.com" in auth_url

        parsed = urlparse(auth_url)
        qs = parse_qs(parsed.query)
        assert "state" in qs
        state = qs["state"][0]

        cb_res = client.get(
            f"/api/v1/accounting/connect/callback?code=stub-auth-code&realmId=stub-realm-12345&state={state}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302, cb_res.text
        location = cb_res.headers["location"]
        assert "/accounting/connection-settings" in location
        assert "status=success" in location

        conn_res = client.get("/api/v1/accounting/connection")
        assert conn_res.status_code == 200, conn_res.text
        conn_data = conn_res.json()
        assert conn_data["status"] == "active"
        assert conn_data["provider"] == "quickbooks"
        assert conn_data["display_name"] == "ProcurePilot Demo Company"
        assert conn_data["connected_at"] is not None
        assert conn_data["disconnected_at"] is None

        created_events = [
            e for e in audit_writer.events if e.action == "accounting.connection_created"
        ]
        assert len(created_events) == 1
        assert created_events[0].tenant_id == context.workspace.tenant_id

        # Any member (e.g. buyer) of the same workspace can read connection status
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        buyer_app, _ = _app(monkeypatch, buyer)
        buyer_client = TestClient(buyer_app, raise_server_exceptions=False)
        buyer_res = buyer_client.get("/api/v1/accounting/connection")
        assert buyer_res.status_code == 200, buyer_res.text
        assert buyer_res.json()["id"] == conn_data["id"]


def test_second_connect_attempt_while_active_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-conflict") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/accounting/connect")
        assert start_res.status_code == 200, start_res.text
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]

        client.get(
            f"/api/v1/accounting/connect/callback?code=code-1&realmId=realm-1&state={state}",
            follow_redirects=False,
        )

        second_res = client.post("/api/v1/accounting/connect")
        assert second_res.status_code == 409, second_res.text


def test_disconnect_preserves_row_and_updates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-disc") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, audit_writer = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/accounting/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client.get(
            f"/api/v1/accounting/connect/callback?code=code-1&realmId=realm-1&state={state}",
            follow_redirects=False,
        )

        disc_res = client.post("/api/v1/accounting/disconnect")
        assert disc_res.status_code == 200, disc_res.text
        disc_data = disc_res.json()
        assert disc_data["status"] == "disconnected"
        assert disc_data["disconnected_at"] is not None

        get_res = client.get("/api/v1/accounting/connection")
        assert get_res.status_code == 200, get_res.text
        assert get_res.json()["status"] == "disconnected"

        # Verify DB directly: row is preserved (not deleted)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select count(*), status from accounting_connection
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
            e for e in audit_writer.events if e.action == "accounting.connection_disconnected"
        ]
        assert len(disc_events) == 1
        assert disc_events[0].tenant_id == context.workspace.tenant_id

        # Disconnecting again when already disconnected returns 404
        second_disc = client.post("/api/v1/accounting/disconnect")
        assert second_disc.status_code == 404, second_disc.text

        # Re-connecting is permitted once disconnected (creates a new active row)
        reconnect_res = client.post("/api/v1/accounting/connect")
        assert reconnect_res.status_code == 200, reconnect_res.text


def test_callback_with_error_or_missing_code_leaves_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("acct-conn-decline") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/accounting/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]

        # Case 1: error parameter from consent denial
        err_res = client.get(
            f"/api/v1/accounting/connect/callback?error=access_denied&state={state}",
            follow_redirects=False,
        )
        assert err_res.status_code == 302, err_res.text
        assert "status=error" in err_res.headers["location"]

        get_res = client.get("/api/v1/accounting/connection")
        assert get_res.status_code == 404, get_res.text

        # Case 2: missing code
        nocode_res = client.get(
            f"/api/v1/accounting/connect/callback?realmId=123&state={state}",
            follow_redirects=False,
        )
        assert nocode_res.status_code == 302, nocode_res.text
        assert "status=error" in nocode_res.headers["location"]

        # Confirm DB has 0 rows for this tenant
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from accounting_connection where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0


def test_cross_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        committed_smart_context("acct-t-a") as ctx_a,
        committed_smart_context("acct-t-b") as ctx_b,
    ):
        owner_a = member_from_workspace(ctx_a.workspace, role=MemberRole.owner)
        owner_b = member_from_workspace(ctx_b.workspace, role=MemberRole.owner)

        app_a, _ = _app(monkeypatch, owner_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)

        start_res = client_a.post("/api/v1/accounting/connect")
        state_a = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        client_a.get(
            f"/api/v1/accounting/connect/callback?code=code-a&realmId=realm-a&state={state_a}",
            follow_redirects=False,
        )

        # Confirm tenant A has an active connection
        assert client_a.get("/api/v1/accounting/connection").status_code == 200

        # Tenant B member querying accounting connection gets 404 (never 403, never tenant A data)
        app_b, _ = _app(monkeypatch, owner_b)
        client_b = TestClient(app_b, raise_server_exceptions=False)

        res_b = client_b.get("/api/v1/accounting/connection")
        assert res_b.status_code == 404, res_b.text

        # Tenant B owner cannot disconnect Tenant A's connection
        disc_b = client_b.post("/api/v1/accounting/disconnect")
        assert disc_b.status_code == 404, disc_b.text
