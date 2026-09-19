"""Integration tests proving purchasing is unaffected by POS connection state (T031, User Story 3).

User Story 3 (specs/015-pos-inventory-integration/spec.md):
"Purchasing keeps working exactly as before if the integration is disconnected or was
never connected (Priority: P3). Every purchasing workflow — comparing offers, building
requests, recording purchases — continues to work exactly as it did before this feature
existed, with manual quantity entry, and with zero loss of previously recorded data."

This test suite proves:
1. Static decoupling (confirmed via grep in Step 1): neither `modules/requests/` nor
   `modules/offers/` references `pos_connection` or `modules.pos` anywhere.
2. Behavioral guarantee:
   - When a tenant has NO POS connection at all (default state):
     * POST /api/v1/requests succeeds with 201 Created and creates a valid purchase request.
     * GET /api/v1/offers/compare succeeds with 200 OK and returns a valid offer comparison.
   - When a tenant has a POS connection in 'needs_reauth' status:
     * POST /api/v1/requests succeeds with 201 Created.
     * GET /api/v1/offers/compare succeeds with 200 OK.
   - When a tenant has a POS connection in 'disconnected' status (disconnected_at set):
     * POST /api/v1/requests succeeds with 201 Created.
     * GET /api/v1/offers/compare succeeds with 200 OK.
   - When a tenant has an 'active' POS connection that is disconnected mid-session:
     * Disconnecting via POST /api/v1/pos/disconnect transitions connection to disconnected.
     * Subsequent purchasing actions (create request, compare offers) continue to succeed
       identically with 2xx responses.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    reset_role,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    PsycopgTableQuery,
    _adapt_value,
    _Response,
)
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.schemas import OfferComparison
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import PurchaseRequest
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del bearer_token
        self.events.append(event)


class _TestTableQuery(PsycopgTableQuery):
    """Adapter supporting single and multi-row inserts for psycopg-backed PostgREST testing."""

    def insert(
        self, payload: dict[str, object] | list[dict[str, object]]
    ) -> _TestTableQuery:
        self._operation = "insert"
        self._payload = payload  # type: ignore[assignment]
        return self

    def _execute_insert(self) -> object:
        if self._payload is None:
            raise AssertionError("insert payload is required")
        if isinstance(self._payload, list):
            if not self._payload:
                return _Response([])
            keys = list(self._payload[0])
            query = sql.SQL("insert into {} ({}) values {} returning *").format(
                sql.Identifier(self._table),
                sql.SQL(",").join(sql.Identifier(key) for key in keys),
                sql.SQL(",").join(
                    sql.SQL("({})").format(
                        sql.SQL(",").join(sql.Placeholder() for _ in keys)
                    )
                    for _ in self._payload
                ),
            )
            params = [
                _adapt_value(key, row[key])
                for row in self._payload
                for key in keys
            ]
            return _Response(self._fetch(query, params))
        return super()._execute_insert()


class _TestSupabaseClient(PsycopgSupabaseClient):
    def table(self, table: str) -> _TestTableQuery:
        return _TestTableQuery(self._conn, table)


def _app(
    monkeypatch: pytest.MonkeyPatch,
    member: object,
    conn: psycopg.Connection,
) -> tuple[FastAPI, RecordingAuditWriter]:
    monkeypatch.setenv("POS_PROVIDER_MODE", "stub")
    settings = settings_for_test_db(monkeypatch)
    audit_writer = RecordingAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.pos.service.get_audit_writer",
        lambda: audit_writer,
    )
    monkeypatch.setattr(
        requests_service_module,
        "get_audit_writer",
        lambda: audit_writer,
    )
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: _TestSupabaseClient(conn),
    )
    app = create_app(settings)
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app, audit_writer


def _make_branch(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id, tenant_id, name, region) "
        "values (%s, %s, 'Main Warehouse Branch', 'GB')",
        (branch_id, workspace.tenant_id),
    )
    return branch_id


def _seed_pos_connection(
    workspace: Workspace,
    *,
    status: str,
) -> UUID:
    """Insert a pos_connection row with the given status directly into the database."""
    conn_id = uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
        with db_conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                insert into pos_connection (
                    id,
                    tenant_id,
                    provider,
                    external_account_id,
                    external_account_name,
                    access_token,
                    refresh_token,
                    status,
                    connected_by,
                    disconnected_at
                ) values (
                    %s, %s, 'square', 'ext-sq-test-account', 'Demo POS Store',
                    'enc-test-access-token', 'enc-test-refresh-token', %s, %s,
                    CASE WHEN %s = 'disconnected' THEN now() ELSE null END
                )
                """,
                (conn_id, workspace.tenant_id, status, workspace.membership_id, status),
            )
            reset_role(cur)
        db_conn.commit()
    return conn_id


def _assert_purchasing_endpoints_succeed(
    client: TestClient,
    *,
    branch_id: UUID,
    product_id: UUID,
) -> tuple[PurchaseRequest, OfferComparison]:
    """Execute both purchasing actions via real HTTP endpoints and assert 2xx responses."""
    # 1. Create a purchase request via POST /api/v1/requests
    request_payload = {
        "branch_id": str(branch_id),
        "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
        "lines": [
            {
                "workspace_product_id": str(product_id),
                "quantity": "5.000000",
                "note": "Purchasing unaffected test line",
            }
        ],
    }
    pr_response = client.post(
        "/api/v1/requests",
        json=request_payload,
        headers={"Authorization": "Bearer test-token"},
    )
    assert pr_response.status_code == 201, (
        f"POST /api/v1/requests failed: {pr_response.status_code}: {pr_response.text}"
    )
    pr_data = pr_response.json()
    assert pr_data["status"] == "draft"
    assert len(pr_data["lines"]) == 1
    assert pr_data["lines"][0]["workspace_product_id"] == str(product_id)
    assert pr_data["lines"][0]["quantity"] == "5.000000"
    purchase_request = PurchaseRequest.model_validate(pr_data)

    # 2. Compare offers via GET /api/v1/offers/compare
    compare_response = client.get(
        "/api/v1/offers/compare",
        params={"product_id": str(product_id), "quantity": "5.000000"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert compare_response.status_code == 200, (
        f"GET /offers/compare failed: {compare_response.status_code}: {compare_response.text}"
    )
    compare_data = compare_response.json()
    assert compare_data["product"]["id"] == str(product_id)
    assert len(compare_data["offers"]) >= 1
    assert compare_data["recommendation"] is not None
    offer_comparison = OfferComparison.model_validate(compare_data)

    return purchase_request, offer_comparison


def test_purchasing_unaffected_when_no_pos_connection_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: Workspace with NO pos_connection creates requests and compares offers normally."""
    with committed_smart_context("pos-none") as context:
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                act_as(cur, context.workspace)
                branch_id = _make_branch(cur, context.workspace)
            db_conn.commit()

            # Seed a costed offer for the product so Smart Compare has real data
            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal("12.5000"),
            )

            # Confirm 0 pos_connection rows exist for this tenant
            with db_conn.cursor() as cur:
                cur.execute(
                    "select count(*) from pos_connection where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                assert cur.fetchone()[0] == 0

            owner = member_from_workspace(context.workspace, role=MemberRole.owner)
            app, _ = _app(monkeypatch, owner, db_conn)
            client = TestClient(app, raise_server_exceptions=False)

            # GET /pos/connection returns 404 (clean not connected)
            assert client.get("/api/v1/pos/connection").status_code == 404

            # Both purchasing endpoints must succeed normally (201 and 200)
            pr, cmp = _assert_purchasing_endpoints_succeed(
                client,
                branch_id=branch_id,
                product_id=context.product_id,
            )
            assert pr.status == "draft"
            assert cmp.recommendation is not None


def test_purchasing_unaffected_when_pos_connection_needs_reauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: Workspace with 'needs_reauth' POS creates requests/compares offers identically."""
    with committed_smart_context("pos-reauth") as context:
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                act_as(cur, context.workspace)
                branch_id = _make_branch(cur, context.workspace)
            db_conn.commit()

            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal("15.0000"),
            )

            conn_id = _seed_pos_connection(context.workspace, status="needs_reauth")

            owner = member_from_workspace(context.workspace, role=MemberRole.owner)
            app, _ = _app(monkeypatch, owner, db_conn)
            client = TestClient(app, raise_server_exceptions=False)

            # GET /pos/connection reflects needs_reauth
            pos_res = client.get("/api/v1/pos/connection")
            assert pos_res.status_code == 200
            assert pos_res.json()["id"] == str(conn_id)
            assert pos_res.json()["status"] == "needs_reauth"

            # Both purchasing endpoints must succeed identically
            pr, cmp = _assert_purchasing_endpoints_succeed(
                client,
                branch_id=branch_id,
                product_id=context.product_id,
            )
            assert pr.status == "draft"
            assert cmp.recommendation is not None


def test_purchasing_unaffected_when_pos_connection_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: Workspace with disconnected POS creates requests and compares offers identically."""
    with committed_smart_context("pos-disc") as context:
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                act_as(cur, context.workspace)
                branch_id = _make_branch(cur, context.workspace)
            db_conn.commit()

            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal("18.0000"),
            )

            conn_id = _seed_pos_connection(context.workspace, status="disconnected")

            # Verify disconnected_at is set in the database
            with db_conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select status, disconnected_at from pos_connection where id = %s",
                    (conn_id,),
                )
                row = cur.fetchone()
                assert row is not None
                assert row["status"] == "disconnected"
                assert row["disconnected_at"] is not None

            owner = member_from_workspace(context.workspace, role=MemberRole.owner)
            app, _ = _app(monkeypatch, owner, db_conn)
            client = TestClient(app, raise_server_exceptions=False)

            # GET /pos/connection reflects disconnected
            pos_res = client.get("/api/v1/pos/connection")
            assert pos_res.status_code == 200
            assert pos_res.json()["id"] == str(conn_id)
            assert pos_res.json()["status"] == "disconnected"
            assert pos_res.json()["disconnected_at"] is not None

            # Both purchasing endpoints must succeed identically
            pr, cmp = _assert_purchasing_endpoints_succeed(
                client,
                branch_id=branch_id,
                product_id=context.product_id,
            )
            assert pr.status == "draft"
            assert cmp.recommendation is not None


def test_disconnecting_active_connection_does_not_disrupt_purchasing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance Scenario 3.2: Disconnecting POS does not disrupt subsequent purchasing."""
    with committed_smart_context("pos-lifecycle") as context:
        with psycopg.connect(TEST_DATABASE_URL or "") as db_conn:
            with db_conn.cursor() as cur:
                act_as(cur, context.workspace)
                branch_id = _make_branch(cur, context.workspace)
            db_conn.commit()

            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal("20.0000"),
            )

            owner = member_from_workspace(context.workspace, role=MemberRole.owner)
            app, _ = _app(monkeypatch, owner, db_conn)
            client = TestClient(app, raise_server_exceptions=False)

            # 1. Connect POS via the real connect + callback flow
            start_res = client.post("/api/v1/pos/connect")
            assert start_res.status_code == 200, start_res.text
            state = parse_qs(urlparse(start_res.json()["authorization_url"]).query)["state"][0]
            cb_res = client.get(
                f"/api/v1/pos/connect/callback?code=stub-auth-code&state={state}",
                follow_redirects=False,
            )
            assert cb_res.status_code == 302
            assert client.get("/api/v1/pos/connection").json()["status"] == "active"

            # 2. Disconnect POS via the real disconnect endpoint
            disc_res = client.post("/api/v1/pos/disconnect")
            assert disc_res.status_code == 200, disc_res.text
            assert disc_res.json()["status"] == "disconnected"

            # 3. Immediately exercise purchasing endpoints — must succeed with no disruption
            pr, cmp = _assert_purchasing_endpoints_succeed(
                client,
                branch_id=branch_id,
                product_id=context.product_id,
            )
            assert pr.status == "draft"
            assert cmp.recommendation is not None
