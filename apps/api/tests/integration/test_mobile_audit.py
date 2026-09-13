"""Mobile-originated audit coverage — task T045 (009-mobile-app-mvp, FR-016).

`test_requests_audit.py` already proves `audit_event` accepts, stores, and immutably retains a
row for every one of `RequestsService`'s action strings — via a direct `record_audit_event` RPC
call plus a source-string check that the service literally emits each string. That is not
duplicated here (re-proving `audit_event`'s generic append-only guarantee for three more action
strings has no additional signal — the trigger does not care which string is in the row).

What is NOT proven anywhere yet: that a real HTTP call through the actual mobile-facing endpoints
(`POST /requests`, `POST /requests/{id}/submit`, `POST /low-stock-reports`) actually results in the
correct row landing in `audit_event` — i.e. that the live request-handling path, not just the
service's own source code, reaches the audit writer. This file closes that gap the same way
`test_idempotent_replay.py` does for the idempotent-replay behavior of the same three endpoints: a
real `TestClient(app)` request against a psycopg-backed fake PostgREST client, since this harness
has no live PostgREST server to hit directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import PsycopgSupabaseClient
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.router import get_requests_service
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for mobile audit-coverage integration tests",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


class _AuditReplayClient(PsycopgSupabaseClient):
    def table(self, name: str) -> _AuditTableQuery:
        return _AuditTableQuery(self._conn, name)


class _AuditTableQuery:
    def __init__(self, conn: psycopg.Connection, table: str) -> None:
        from integration.quotation_helpers import PsycopgTableQuery

        self._conn = conn
        self._delegate = PsycopgTableQuery(conn, table)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 -- proxies an untyped delegate
        return getattr(self._delegate, name)

    def insert(
        self, payload: dict[str, object] | list[dict[str, object]]
    ) -> _AuditTableQuery:
        self._delegate.insert(payload)  # type: ignore[arg-type]
        return self

    def execute(self) -> object:
        with self._conn.cursor() as cur:
            cur.execute("savepoint mobile_audit_client")
        try:
            response = self._delegate.execute()
        except psycopg.errors.UniqueViolation as exc:
            with self._conn.cursor() as cur:
                cur.execute("rollback to savepoint mobile_audit_client")
            raise APIError(
                {"code": "23505", "message": str(exc), "details": "", "hint": ""}
            ) from exc
        else:
            with self._conn.cursor() as cur:
                cur.execute("release savepoint mobile_audit_client")
            return response


class _PsycopgAuditWriter:
    """Records through the real `record_audit_event` SECURITY DEFINER function, the same one
    `AuditWriter.record` calls in production — proving the actual DB-level append-only path,
    not a mock of the writer's own behavior."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del bearer_token
        with self._conn.cursor() as cur:
            cur.execute(
                "select record_audit_event("
                "%s, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s"
                ")",
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


def _make_branch(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Audit Branch','GB')",
        (branch_id, workspace.tenant_id),
    )
    return branch_id


def _member(workspace: Workspace) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}-{workspace.role}@example.test",
        role=MemberRole(workspace.role),
    )


def _test_settings() -> Settings:
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


def _insert_lines(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    request_id: str,
    payload_lines: list[object],
    estimates: list[LineEstimate],
) -> list[dict[str, object]]:
    del estimates
    rows: list[dict[str, object]] = []
    with conn.cursor(row_factory=dict_row) as cur:
        for line in payload_lines:
            cur.execute(
                "insert into purchase_request_line "
                "(tenant_id,purchase_request_id,workspace_product_id,quantity,note) "
                "values (%s,%s,%s,%s,%s) returning *",
                (
                    tenant_id,
                    request_id,
                    str(line.workspace_product_id),
                    line.quantity,
                    line.note,
                ),
            )
            rows.append(dict(cur.fetchone()))
    return rows


def _client_for(
    conn: psycopg.Connection,
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    def client_factory(_settings: object, _token: str) -> _AuditReplayClient:
        return _AuditReplayClient(conn)

    service = RequestsService.__new__(RequestsService)
    # A bare object() was enough for create_request/submit_request (only ever passed through to
    # authenticated_client, itself monkeypatched above) but approve_request's own
    # _decide_and_notify opens a SEPARATE raw psycopg connection via
    # self._settings.database_url.get_secret_value() for its atomic multi-write transaction
    # (Wave 9's own approved->ordered change) -- it needs a real Settings with a real
    # database_url, matching test_decision_atomicity.py's own precedent for exercising that exact
    # method against real Postgres.
    service._settings = _test_settings()
    service._estimate_products = lambda product_ids: [
        LineEstimate(None, None, None) for _product_id in product_ids
    ]
    service._insert_lines = lambda client, **kwargs: _insert_lines(conn, **kwargs)
    service._budget_status_for = lambda _client, _request_row: None

    monkeypatch.setattr(requests_service_module, "authenticated_client", client_factory)
    monkeypatch.setattr(
        requests_service_module,
        "get_audit_writer",
        lambda: _PsycopgAuditWriter(conn),
    )

    app = create_app(settings=_test_settings())
    app.dependency_overrides[current_member] = lambda: _member(workspace)
    app.dependency_overrides[get_requests_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def _audit_row(
    cur: psycopg.Cursor, *, tenant_id: UUID, action: str
) -> tuple[str, dict[str, object]] | None:
    cur.execute(
        "select outcome, target from audit_event where tenant_id = %s and action = %s",
        (tenant_id, action),
    )
    return cur.fetchone()


def test_post_requests_records_purchase_request_created(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-create")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Widget")
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        payload = {
            "branch_id": str(branch_id),
            "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
            "lines": [
                {"workspace_product_id": str(product_id), "quantity": "3.000000"}
            ],
        }
        response = client.post(
            "/api/v1/requests",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201, response.text
        request_id = response.json()["id"]

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.purchase_request_created"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {"purchase_request_id": request_id}


def test_post_requests_submit_records_purchase_request_submitted(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-submit")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Submit Widget")
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        headers = {"Authorization": "Bearer test-token"}
        created = client.post(
            "/api/v1/requests",
            json={
                "branch_id": str(branch_id),
                "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
                "lines": [
                    {"workspace_product_id": str(product_id), "quantity": "3.000000"}
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]

        submitted = client.post(
            f"/api/v1/requests/{request_id}/submit", headers=headers
        )
        assert submitted.status_code == 200, submitted.text

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.purchase_request_submitted"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {"purchase_request_id": request_id}


def test_post_low_stock_reports_records_low_stock_report_created(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-low-stock")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Milk")
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        response = client.post(
            "/api/v1/low-stock-reports",
            json={
                "branch_id": str(branch_id),
                "workspace_product_id": str(product_id),
                "count_remaining": "2.000000",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201, response.text
        report_id = response.json()["id"]

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.low_stock_report_created"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {"low_stock_report_id": report_id}


# ── T034 (010-mobile-approvals-receipt): mobile approvals/receipt audit coverage ──
#
# Same gap this file was written to close, for three more actions this chunk adds: a real
# TestClient(app) round trip through the actual endpoints, not just a check that the service's
# own source code emits the right action string. `workspace` is the OWNER in every case here
# (make_workspace's own row), so `_require_assigned_approver_or_owner`'s and
# `_authorize_delivery_confirmation`'s owner-bypass branches let one caller drive
# create -> submit -> approve -> confirm-delivery -> quality-issue without any extra
# branch-assignment plumbing.


def test_post_requests_approve_records_approval_step_approved(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-approve")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Approve Widget")
    # approve_request's own _decide_and_notify opens a SEPARATE raw psycopg connection (its own
    # atomic multi-write transaction, Wave 9's approved->ordered change) -- that connection can
    # only see this fixture's rows once they're actually committed, not merely written on `conn`'s
    # own still-open transaction (matches test_decision_atomicity.py's own precedent for this
    # exact situation).
    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        headers = {"Authorization": "Bearer test-token"}
        created = client.post(
            "/api/v1/requests",
            json={
                "branch_id": str(branch_id),
                "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
                "lines": [
                    {"workspace_product_id": str(product_id), "quantity": "3.000000"}
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]

        submitted = client.post(
            f"/api/v1/requests/{request_id}/submit", headers=headers
        )
        assert submitted.status_code == 200, submitted.text
        approval_step_id = submitted.json()["approval_step"]["id"]

    # Same reasoning as the earlier commit: the request/step just created+submitted via `conn`
    # are only visible to _decide_and_notify's own separate connection once committed here.
    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)
        approved = client.post(
            f"/api/v1/requests/{request_id}/approve",
            json={"comment": "Approved for audit coverage"},
            headers=headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "ordered"

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.approval_step_approved"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {
            "purchase_request_id": request_id,
            "approval_step_id": approval_step_id,
            "decided_by_membership_id": str(workspace.membership_id),
        }


def test_post_confirm_delivery_records_delivery_confirmed(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-delivery")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Delivery Widget")
    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        headers = {"Authorization": "Bearer test-token"}
        created = client.post(
            "/api/v1/requests",
            json={
                "branch_id": str(branch_id),
                "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
                "lines": [
                    {"workspace_product_id": str(product_id), "quantity": "3.000000"}
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]
        line_id = created.json()["lines"][0]["id"]

        submitted = client.post(
            f"/api/v1/requests/{request_id}/submit", headers=headers
        )
        assert submitted.status_code == 200, submitted.text

    # approve_request's own _decide_and_notify opens a separate connection that needs the
    # just-submitted request/step actually committed to see them (see the earlier test's own
    # comment for the full explanation).
    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)
        approved = client.post(
            f"/api/v1/requests/{request_id}/approve", json={}, headers=headers
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "ordered"

        confirmed = client.post(
            f"/api/v1/requests/{request_id}/confirm-delivery",
            json={
                "lines": [
                    {"purchase_request_line_id": line_id, "quantity_received": "3.000000"}
                ]
            },
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "delivered"

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.delivery_confirmed"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {"purchase_request_id": request_id}


def test_post_quality_issues_records_quality_issue_reported(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "mobile-audit-quality")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Audit Quality Widget")
    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        headers = {"Authorization": "Bearer test-token"}
        created = client.post(
            "/api/v1/requests",
            json={
                "branch_id": str(branch_id),
                "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
                "lines": [
                    {"workspace_product_id": str(product_id), "quantity": "3.000000"}
                ],
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]
        line_id = created.json()["lines"][0]["id"]

        submitted = client.post(
            f"/api/v1/requests/{request_id}/submit", headers=headers
        )
        assert submitted.status_code == 200, submitted.text

    conn.commit()
    with conn.cursor() as cur:
        act_as(cur, workspace)
        approved = client.post(
            f"/api/v1/requests/{request_id}/approve", json={}, headers=headers
        )
        assert approved.status_code == 200, approved.text

        confirmed = client.post(
            f"/api/v1/requests/{request_id}/confirm-delivery",
            json={
                "lines": [
                    {"purchase_request_line_id": line_id, "quantity_received": "3.000000"}
                ]
            },
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text

        reported = client.post(
            f"/api/v1/requests/{request_id}/quality-issues",
            json={"description": "Box arrived crushed"},
            headers=headers,
        )
        assert reported.status_code == 201, reported.text
        issue_id = reported.json()["id"]

        row = _audit_row(
            cur, tenant_id=workspace.tenant_id, action="requests.quality_issue_reported"
        )
        assert row is not None
        outcome, target = row
        assert outcome == "success"
        assert target == {"delivery_quality_issue_id": issue_id}
