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

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

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
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.accounting.connector import OAuthTokens, StubConnector
from procurepilot_api.modules.accounting.service import _get_signing_secret
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


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> tuple[FastAPI, RecordingAuditWriter]:
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
        redirect = urlparse(location)
        assert redirect.path == "/accounting"
        assert parse_qs(redirect.query) == {
            "accounting_code": ["stub-auth-code"],
            "accounting_state": [state],
            "realm_id": ["stub-realm-12345"],
        }

        comp_res = client.post(
            "/api/v1/accounting/connect/complete",
            json={
                "code": "stub-auth-code",
                "state": state,
                "realm_id": "stub-realm-12345",
            },
        )
        assert comp_res.status_code == 201, comp_res.text

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

        cb_res = client.get(
            f"/api/v1/accounting/connect/callback?code=code-1&realmId=realm-1&state={state}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302
        assert "accounting_code=code-1" in cb_res.headers["location"]
        comp_res = client.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "code-1", "state": state, "realm_id": "realm-1"},
        )
        assert comp_res.status_code == 201

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
        cb_res = client.get(
            f"/api/v1/accounting/connect/callback?code=code-1&realmId=realm-1&state={state}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302
        assert "accounting_code=code-1" in cb_res.headers["location"]
        comp_res = client.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "code-1", "state": state, "realm_id": "realm-1"},
        )
        assert comp_res.status_code == 201

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
        assert "accounting_connected=failed" in err_res.headers["location"]

        get_res = client.get("/api/v1/accounting/connection")
        assert get_res.status_code == 404, get_res.text

        # Case 2: missing code
        nocode_res = client.get(
            f"/api/v1/accounting/connect/callback?realmId=123&state={state}",
            follow_redirects=False,
        )
        assert nocode_res.status_code == 302, nocode_res.text
        assert "accounting_connected=failed" in nocode_res.headers["location"]

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
        cb_res = client_a.get(
            f"/api/v1/accounting/connect/callback?code=code-a&realmId=realm-a&state={state_a}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302
        assert "accounting_code=code-a" in cb_res.headers["location"]
        comp_res = client_a.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "code-a", "state": state_a, "realm_id": "realm-a"},
        )
        assert comp_res.status_code == 201

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


def test_cross_tenant_state_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """a. owner of tenant A completes with tenant B's validly signed state -> 404,
    no connection in A or B, connector token exchange never called."""
    with (
        committed_smart_context("acct-cross-a") as ctx_a,
        committed_smart_context("acct-cross-b") as ctx_b,
    ):
        owner_a = member_from_workspace(ctx_a.workspace, role=MemberRole.owner)
        owner_b = member_from_workspace(ctx_b.workspace, role=MemberRole.owner)

        app_b, _ = _app(monkeypatch, owner_b)
        client_b = TestClient(app_b, raise_server_exceptions=False)
        start_res_b = client_b.post("/api/v1/accounting/connect")
        assert start_res_b.status_code == 200
        state_b = parse_qs(urlparse(start_res_b.json()["authorization_url"]).query)["state"][0]

        app_a, _ = _app(monkeypatch, owner_a)
        client_a = TestClient(app_a, raise_server_exceptions=False)

        exchange_called = []
        original_exchange = StubConnector.exchange_code_for_tokens

        def spy_exchange(
            self: object, code: str, redirect_uri: str, realm_id: str | None = None
        ) -> OAuthTokens:
            exchange_called.append(code)
            return original_exchange(self, code, redirect_uri, realm_id)

        monkeypatch.setattr(StubConnector, "exchange_code_for_tokens", spy_exchange)

        res = client_a.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "stub-code", "state": state_b, "realm_id": "realm-b"},
        )
        assert res.status_code == 404, res.text
        assert res.json()["details"] == {"resource": "oauth_state"}
        assert len(exchange_called) == 0

        # No connection row in A or B
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from accounting_connection where tenant_id in (%s, %s)",
                    (ctx_a.workspace.tenant_id, ctx_b.workspace.tenant_id),
                )
                assert cur.fetchone()[0] == 0


def test_complete_requires_owner_and_matching_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """b. non-owner role -> 403; second OWNER-role membership of same tenant -> 404
    (mismatched membership).
    """
    with committed_smart_context("acct-rbac-comp") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)

        app_owner, _ = _app(monkeypatch, owner)
        client_owner = TestClient(app_owner, raise_server_exceptions=False)
        start_res = client_owner.post("/api/v1/accounting/connect")
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]

        # Non-owner buyer gets 403
        app_buyer, _ = _app(monkeypatch, buyer)
        client_buyer = TestClient(app_buyer, raise_server_exceptions=False)
        res_buyer = client_buyer.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "stub-code", "state": state, "realm_id": "realm-1"},
        )
        assert res_buyer.status_code == 403, res_buyer.text

        # A second OWNER-role membership in the same tenant has mismatched membership_id -> 404
        second_owner = CurrentMember(
            membership_id=uuid4(),
            tenant_id=context.workspace.tenant_id,
            user_id=uuid4(),
            email=f"{context.workspace.label}-owner2@example.test",
            role=MemberRole.owner,
        )
        app_second_owner, _ = _app(monkeypatch, second_owner)
        client_second_owner = TestClient(app_second_owner, raise_server_exceptions=False)
        res_second_owner = client_second_owner.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "stub-code", "state": state, "realm_id": "realm-1"},
        )
        assert res_second_owner.status_code == 404, res_second_owner.text
        assert res_second_owner.json()["details"] == {"resource": "oauth_state"}


def test_expired_state_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """c. state older than 600 s -> 422, no row."""
    with committed_smart_context("acct-exp-state") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        settings = settings_for_test_db(monkeypatch)
        payload = {
            "tenant_id": str(owner.tenant_id),
            "membership_id": str(owner.membership_id),
            "user_id": str(owner.user_id),
            "email": owner.email,
            "role": owner.role.value,
            "provider": "quickbooks",
            "mode": "stub",
            "iat": int(time.time()) - 605,
            "nonce": secrets.token_hex(16),
        }
        data_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        secret = _get_signing_secret(settings)
        signature = hmac.new(secret, data_bytes, hashlib.sha256).digest()
        expired_state = (
            f"{base64.urlsafe_b64encode(data_bytes).decode('ascii')}."
            f"{base64.urlsafe_b64encode(signature).decode('ascii')}"
        )

        res = client.post(
            "/api/v1/accounting/connect/complete",
            json={"code": "stub-code", "state": expired_state, "realm_id": "realm-1"},
        )
        assert res.status_code == 422, res.text
        assert res.json()["details"] == {"reason": "invalid_state"}

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from accounting_connection where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0


def test_callback_tampered_signature_redirects_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """d. callback with a tampered state signature -> failure redirect, nothing written."""
    with committed_smart_context("acct-tampered") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        app, _ = _app(monkeypatch, owner)
        client = TestClient(app, raise_server_exceptions=False)

        start_res = client.post("/api/v1/accounting/connect")
        assert start_res.status_code == 200
        state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
        data_b64, _ = state.split(".", 1)
        tampered_state = f"{data_b64}.tampered_signature"

        cb_res = client.get(
            f"/api/v1/accounting/connect/callback?code=stub-code&realmId=realm-1&state={tampered_state}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302
        assert "accounting_connected=failed" in cb_res.headers["location"]
        assert "error=authorization_failed" in cb_res.headers["location"]

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from accounting_connection where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0


def test_unauthenticated_post_complete_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """e. unauthenticated POST complete -> 401."""
    monkeypatch.setenv("ACCOUNTING_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    res = client.post(
        "/api/v1/accounting/connect/complete",
        json={"code": "stub-code", "state": "some-state", "realm_id": "realm-1"},
    )
    assert res.status_code == 401, res.text
