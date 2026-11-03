"""Integration tests for single-request submit and withdraw idempotent replay (PPS-190).

Proves:
(a) submit twice with the same key returns 200 with same id/status, exactly ONE audit row and
    ONE approval_step;
(b) submit twice with different keys returns 409 not_draft;
(c) withdraw twice with the same key returns 200 with same id/status, exactly ONE audit row;
    withdraw with different key returns 409;
(d) submit replay does not re-run estimation (updated_at unchanged);
(e) submit/withdraw without key preserves existing behaviour (no idempotency_key in audit
    target, second call gets 409);
(f) submit and withdraw replays are scoped to the actor (a different member calling
    submit gets 409 not_draft, calling withdraw gets 409 already_decided_or_withdrawn;
    same member replaying gets 200).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    connection,
    delete_tenant_scoped_rows,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.test_purchase_requests import (
    _add_line_no_estimate,
    _current_member,
    _make_branch,
    _make_member,
    _make_request,
    _TestSupabaseClient,
)
from procurepilot_api.config import Settings
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.router import get_requests_service
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL required; needs Postgres with migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


class _PsycopgAuditWriter:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del bearer_token
        with self._conn.cursor() as cur:
            cur.execute(
                "select record_audit_event(%s, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s)",
                (
                    event.action,
                    event.outcome,
                    event.tenant_id,
                    event.actor_membership_id,
                    event.actor_email,
                    Jsonb(event.target),
                    event.trace_id,
                ),
            )


def _test_settings() -> Settings:
    from pydantic import SecretStr

    return Settings(
        API_HOST="127.0.0.1",
        API_PORT=8000,
        API_ENV="local",
        API_LOG_LEVEL="error",
        API_CORS_ORIGINS="http://localhost:4200",
        SUPABASE_URL="http://localhost:54321",
        SUPABASE_ANON_KEY=SecretStr("anon"),
        SUPABASE_SERVICE_ROLE_KEY=SecretStr("service"),
        SUPABASE_JWT_AUDIENCE="authenticated",
        SUPABASE_JWT_ISSUER="http://localhost:54321/auth/v1",
        DATABASE_URL=SecretStr(TEST_DATABASE_URL or ""),
        PLATFORM_INVITATION_TTL_DAYS=7,
        MEMBER_INVITATION_TTL_DAYS=7,
        RATE_LIMIT_AUTH="100/minute",
        WEB_API_BASE_URL="http://localhost:8000/api/v1",
        WEB_DEFAULT_LOCALE="en",
    )


def _build_test_client(
    conn: psycopg.Connection,
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor: Workspace | None = None,
) -> tuple[TestClient, RequestsService]:
    service = RequestsService(settings=_test_settings())
    active_actor = actor or workspace

    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, token: _TestSupabaseClient(
            conn, claims=token if (token and token.startswith("{")) else None
        ),
    )
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda product_ids, **_kw: [
            LineEstimate(
                unit_price_amount=Decimal("15.5000"),
                unit_price_currency="GBP",
                source_landed_cost_id=None,
            )
            for _ in product_ids
        ],
    )
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(service, "_fetch_threshold_rules", lambda _client: [])
    monkeypatch.setattr(service, "_fetch_active_delegations", lambda _client, **_kw: [])
    monkeypatch.setattr(service, "_fetch_removed_membership_ids", lambda _client: set())
    monkeypatch.setattr(
        service, "_fetch_owner_membership_id", lambda _client: workspace.membership_id
    )
    monkeypatch.setattr(
        requests_service_module,
        "get_audit_writer",
        lambda: _PsycopgAuditWriter(conn),
    )

    app = create_app(settings=_test_settings())
    app.dependency_overrides[current_member] = lambda: _current_member(workspace, active_actor)
    app.dependency_overrides[bearer_token] = lambda: active_actor.claims()
    app.dependency_overrides[get_requests_service] = lambda: service

    client = TestClient(app, raise_server_exceptions=False)
    return client, service


def _create_draft_request_with_line(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    product_id: UUID,
    *,
    requester: Workspace | None = None,
) -> UUID:
    actor = requester or workspace
    request_id = _make_request(
        cur,
        workspace,
        branch_id,
        status="draft",
        requested_by_membership_id=actor.membership_id,
    )
    _add_line_no_estimate(cur, workspace, request_id, product_id)
    return request_id


def test_submit_twice_with_same_key_returns_200_and_single_audit_and_step(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-sub-same")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Submit Replay Item")
        request_id = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
    conn.commit()

    try:
        client, _ = _build_test_client(conn, workspace, monkeypatch)
        key = uuid4()
        headers = {"Idempotency-Key": str(key)}

        # Call 1: First submit
        res1 = client.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res1.status_code == 200, res1.text
        data1 = res1.json()
        assert data1["id"] == str(request_id)
        assert data1["status"] == "submitted"

        # Call 2: Replay with the exact same key
        res2 = client.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res2.status_code == 200, res2.text
        data2 = res2.json()
        assert data2["id"] == str(request_id)
        assert data2["status"] == "submitted"

        # Database asserts: exactly ONE submit audit row and ONE approval_step
        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute(
                "select action, outcome, target from audit_event "
                "where tenant_id = %s and action = %s",
                (workspace.tenant_id, "requests.purchase_request_submitted"),
            )
            audit_rows = cur.fetchall()
            assert len(audit_rows) == 1, (
                f"Expected 1 audit row, got {len(audit_rows)}: {audit_rows}"
            )
            assert audit_rows[0]["target"]["purchase_request_id"] == str(request_id)
            assert audit_rows[0]["target"]["idempotency_key"] == str(key)

            cur.execute(
                "select count(*) as cnt from approval_step "
                "where tenant_id = %s and purchase_request_id = %s",
                (workspace.tenant_id, request_id),
            )
            assert cur.fetchone()["cnt"] == 1
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def test_submit_twice_with_different_keys_returns_409_not_draft(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-sub-diff")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Submit Diff Key Item")
        request_id = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
    conn.commit()

    try:
        client, _ = _build_test_client(conn, workspace, monkeypatch)
        key1 = uuid4()
        key2 = uuid4()

        # Call 1: Submit with key1
        res1 = client.post(
            f"/api/v1/requests/{request_id}/submit", headers={"Idempotency-Key": str(key1)}
        )
        assert res1.status_code == 200, res1.text
        assert res1.json()["status"] == "submitted"

        # Call 2: Submit with different key2
        res2 = client.post(
            f"/api/v1/requests/{request_id}/submit", headers={"Idempotency-Key": str(key2)}
        )
        assert res2.status_code == 409, res2.text
        assert res2.json()["details"] == {"reason": "not_draft"}
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def test_withdraw_idempotent_replay_and_conflict(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-withdr")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Withdraw Replay Item")
        request_id = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
    conn.commit()

    try:
        client, _ = _build_test_client(conn, workspace, monkeypatch)
        key = uuid4()
        headers = {"Idempotency-Key": str(key)}

        # Call 1: Withdraw with key
        res1 = client.post(f"/api/v1/requests/{request_id}/withdraw", headers=headers)
        assert res1.status_code == 200, res1.text
        data1 = res1.json()
        assert data1["id"] == str(request_id)
        assert data1["status"] == "withdrawn"

        # Call 2: Replay with same key returns the withdrawn request
        res2 = client.post(f"/api/v1/requests/{request_id}/withdraw", headers=headers)
        assert res2.status_code == 200, res2.text
        data2 = res2.json()
        assert data2["id"] == str(request_id)
        assert data2["status"] == "withdrawn"

        # Verify exactly ONE audit row for requests.purchase_request_withdrawn with idempotency_key
        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute(
                "select action, outcome, target from audit_event "
                "where tenant_id = %s and action = %s",
                (workspace.tenant_id, "requests.purchase_request_withdrawn"),
            )
            audit_rows = cur.fetchall()
            assert len(audit_rows) == 1, (
                f"Expected 1 audit row, got {len(audit_rows)}: {audit_rows}"
            )
            assert audit_rows[0]["target"]["purchase_request_id"] == str(request_id)
            assert audit_rows[0]["target"]["idempotency_key"] == str(key)

        # Call 3: Withdraw with a DIFFERENT key returns 409 already_decided_or_withdrawn
        diff_key = uuid4()
        res3 = client.post(
            f"/api/v1/requests/{request_id}/withdraw", headers={"Idempotency-Key": str(diff_key)}
        )
        assert res3.status_code == 409, res3.text
        assert res3.json()["details"] == {"reason": "already_decided_or_withdrawn"}
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def test_submit_replay_does_not_rerun_estimation(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-no-reest")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Estimation Test Item")
        request_id = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
    conn.commit()

    try:
        client, _ = _build_test_client(conn, workspace, monkeypatch)
        key = uuid4()
        headers = {"Idempotency-Key": str(key)}

        # Call 1: Submit
        res1 = client.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res1.status_code == 200, res1.text

        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute("select updated_at from purchase_request where id = %s", (request_id,))
            updated_at_1 = cur.fetchone()["updated_at"]

        # Call 2: Replay
        res2 = client.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res2.status_code == 200, res2.text

        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute("select updated_at from purchase_request where id = %s", (request_id,))
            updated_at_2 = cur.fetchone()["updated_at"]

        assert updated_at_1 == updated_at_2, f"updated_at changed: {updated_at_1} vs {updated_at_2}"
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def test_existing_behaviour_without_key_unchanged(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-no-key")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="No Key Item")
        req1 = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
        req2 = _create_draft_request_with_line(cur, workspace, branch_id, product_id)
    conn.commit()

    try:
        client, _ = _build_test_client(conn, workspace, monkeypatch)

        # Submit without key: works as today
        res1 = client.post(f"/api/v1/requests/{req1}/submit")
        assert res1.status_code == 200, res1.text
        assert res1.json()["status"] == "submitted"

        # Assert audit event target does NOT contain idempotency_key
        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute(
                "select target from audit_event where tenant_id = %s and action = %s "
                "and target->>'purchase_request_id' = %s",
                (workspace.tenant_id, "requests.purchase_request_submitted", str(req1)),
            )
            row = cur.fetchone()
            assert row is not None
            assert "idempotency_key" not in row["target"]

        # Second submit without key: 409 not_draft
        res1_retry = client.post(f"/api/v1/requests/{req1}/submit")
        assert res1_retry.status_code == 409, res1_retry.text
        assert res1_retry.json()["details"] == {"reason": "not_draft"}

        # Withdraw without key: works as today
        res2 = client.post(f"/api/v1/requests/{req2}/withdraw")
        assert res2.status_code == 200, res2.text
        assert res2.json()["status"] == "withdrawn"

        # Assert audit event target does NOT contain idempotency_key
        with conn.cursor(row_factory=dict_row) as cur:
            reset_role(cur)
            cur.execute(
                "select target from audit_event where tenant_id = %s and action = %s "
                "and target->>'purchase_request_id' = %s",
                (workspace.tenant_id, "requests.purchase_request_withdrawn", str(req2)),
            )
            row2 = cur.fetchone()
            assert row2 is not None
            assert "idempotency_key" not in row2["target"]

        # Second withdraw without key: 409 already_decided_or_withdrawn
        res2_retry = client.post(f"/api/v1/requests/{req2}/withdraw")
        assert res2_retry.status_code == 409, res2_retry.text
        assert res2_retry.json()["details"] == {"reason": "already_decided_or_withdrawn"}
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def test_submit_replay_scoped_to_actor(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-sub-actor-owner")
        member_a = _make_member(cur, workspace.tenant_id, "pr-idem-sub-a", "branch_manager")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Submit Actor Item")
        request_id = _create_draft_request_with_line(
            cur, workspace, branch_id, product_id, requester=member_a
        )
    conn.commit()

    try:
        client_a, _ = _build_test_client(conn, workspace, monkeypatch, actor=member_a)
        client_b, _ = _build_test_client(conn, workspace, monkeypatch, actor=workspace)
        key = uuid4()
        headers = {"Idempotency-Key": str(key)}

        # Call 1: Member A submits with key K -> 200
        res_a1 = client_a.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res_a1.status_code == 200, res_a1.text
        assert res_a1.json()["status"] == "submitted"

        # Call 2: Member B (owner) calls submit with key K -> must NOT replay A's result
        # (it gets normal 409 not_draft)
        res_b = client_b.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res_b.status_code == 409, f"Expected 409, got {res_b.status_code}: {res_b.text}"
        assert res_b.json()["details"] == {"reason": "not_draft"}

        # Call 3: Member A replaying with key K still gets 200
        res_a2 = client_a.post(f"/api/v1/requests/{request_id}/submit", headers=headers)
        assert res_a2.status_code == 200, res_a2.text
        assert res_a2.json()["status"] == "submitted"
        assert res_a2.json()["id"] == str(request_id)
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            cur.execute("delete from auth.users where id = %s", (member_a.user_id,))
            conn.commit()


def test_withdraw_replay_scoped_to_actor(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "pr-idem-wdr-actor-owner")
        member_a = _make_member(cur, workspace.tenant_id, "pr-idem-wdr-a", "branch_manager")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Withdraw Actor Item")
        request_id = _create_draft_request_with_line(
            cur, workspace, branch_id, product_id, requester=member_a
        )
    conn.commit()

    try:
        client_a, _ = _build_test_client(conn, workspace, monkeypatch, actor=member_a)
        client_b, _ = _build_test_client(conn, workspace, monkeypatch, actor=workspace)
        key = uuid4()
        headers = {"Idempotency-Key": str(key)}

        # Call 1: Member A withdraws with key K -> 200
        res_a1 = client_a.post(f"/api/v1/requests/{request_id}/withdraw", headers=headers)
        assert res_a1.status_code == 200, res_a1.text
        assert res_a1.json()["status"] == "withdrawn"

        # Call 2: Member B (owner) calls withdraw with key K -> must NOT replay A's result
        # (it gets normal 409 already_decided_or_withdrawn)
        res_b = client_b.post(f"/api/v1/requests/{request_id}/withdraw", headers=headers)
        assert res_b.status_code == 409, f"Expected 409, got {res_b.status_code}: {res_b.text}"
        assert res_b.json()["details"] == {"reason": "already_decided_or_withdrawn"}

        # Call 3: Member A replaying with key K still gets 200
        res_a2 = client_a.post(f"/api/v1/requests/{request_id}/withdraw", headers=headers)
        assert res_a2.status_code == 200, res_a2.text
        assert res_a2.json()["status"] == "withdrawn"
        assert res_a2.json()["id"] == str(request_id)
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
            cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
            cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            cur.execute("delete from auth.users where id = %s", (member_a.user_id,))
            conn.commit()
