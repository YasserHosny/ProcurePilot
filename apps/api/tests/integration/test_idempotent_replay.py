"""API-level idempotent replay coverage for already-idempotent request mutations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from psycopg import sql
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
    reason="TEST_DATABASE_URL is required for idempotent replay integration tests",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


class _PsycopgReplayClient(PsycopgSupabaseClient):
    def table(self, name: str) -> _ReplayTableQuery:
        return _ReplayTableQuery(self._conn, name)


class _ReplayTableQuery:
    def __init__(self, conn: psycopg.Connection, table: str) -> None:
        from integration.quotation_helpers import PsycopgTableQuery

        self._conn = conn
        self._delegate = PsycopgTableQuery(conn, table)

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 -- proxies an untyped delegate
        return getattr(self._delegate, name)

    def insert(
        self, payload: dict[str, object] | list[dict[str, object]]
    ) -> _ReplayTableQuery:
        self._delegate.insert(payload)  # type: ignore[arg-type]
        return self

    def execute(self) -> object:
        with self._conn.cursor() as cur:
            cur.execute("savepoint idempotent_replay_client")
        try:
            response = self._delegate.execute()
        except psycopg.errors.UniqueViolation as exc:
            with self._conn.cursor() as cur:
                cur.execute("rollback to savepoint idempotent_replay_client")
            raise APIError(
                {
                    "code": "23505",
                    "message": str(exc),
                    "details": "",
                    "hint": "",
                }
            ) from exc
        else:
            with self._conn.cursor() as cur:
                cur.execute("release savepoint idempotent_replay_client")
            return response


class _PsycopgAuditWriter:
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
        "insert into branch (id,tenant_id,name,region) "
        "values (%s,%s,'Replay Branch','GB')",
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
    def client_factory(_settings: object, _token: str) -> _PsycopgReplayClient:
        return _PsycopgReplayClient(conn)

    service = RequestsService.__new__(RequestsService)
    service._settings = object()
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


def _count_rows(cur: psycopg.Cursor, table: str, tenant_id: UUID) -> int:
    cur.execute(
        sql.SQL("select count(*) from {} where tenant_id = %s").format(
            sql.Identifier(table)
        ),
        (tenant_id,),
    )
    return int(cur.fetchone()[0])


def test_post_requests_replay_returns_original_request_without_second_row(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "idempotent-request")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Replay Widget")
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        key = str(uuid4())
        payload = {
            "branch_id": str(branch_id),
            "required_by_date": (date.today() + timedelta(days=7)).isoformat(),
            "lines": [
                {
                    "workspace_product_id": str(product_id),
                    "quantity": "3.000000",
                }
            ],
        }
        headers = {"Authorization": "Bearer test-token", "Idempotency-Key": key}

        first = client.post("/api/v1/requests", json=payload, headers=headers)
        replay = client.post("/api/v1/requests", json=payload, headers=headers)

        assert first.status_code == 201, first.text
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == first.json()["id"]
        assert _count_rows(cur, "purchase_request", workspace.tenant_id) == 1


def test_post_low_stock_reports_replay_returns_original_report_without_second_row(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "idempotent-low-stock")
        branch_id = _make_branch(cur, workspace)
        product_id = make_workspace_product(cur, workspace, name="Replay Milk")
        act_as(cur, workspace)

        client = _client_for(conn, workspace, monkeypatch)
        key = str(uuid4())
        payload = {
            "branch_id": str(branch_id),
            "workspace_product_id": str(product_id),
            "count_remaining": "2.000000",
        }
        headers = {"Authorization": "Bearer test-token", "Idempotency-Key": key}

        first = client.post("/api/v1/low-stock-reports", json=payload, headers=headers)
        replay = client.post("/api/v1/low-stock-reports", json=payload, headers=headers)

        assert first.status_code == 201, first.text
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == first.json()["id"]
        assert _count_rows(cur, "low_stock_report", workspace.tenant_id) == 1
