"""Decision audit, validation and RLS through the HTTP and database paths."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace, reset_role
from integration.quotation_helpers import PsycopgSupabaseClient
from integration.test_approvals import _make_branch, _make_pending_step, _make_submitted_request
from integration.test_purchase_requests import _current_member
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import AppError, app_error_handler
from procurepilot_api.modules.requests import router
from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.router import get_requests_service
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    # Service transactions use savepoints inside this test-owned transaction. All test
    # rows, including append-only audit events, disappear when the outer scope rolls back.
    with module.db.connect(TEST_DATABASE_URL or "") as connection:
        connection.execute("select 1")
        try:
            yield connection
        finally:
            connection.rollback()


def seed(conn: psycopg.Connection) -> tuple[Workspace, UUID, UUID]:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "single-decision")
        branch = _make_branch(cur, ws)
        rid = _make_submitted_request(cur, ws, branch)
        sid = _make_pending_step(cur, ws.tenant_id, rid, ws.membership_id)
    return ws, rid, sid


@contextmanager
def api_as(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    ws: Workspace,
    *,
    fail_audit: bool = False,
    fail_response: bool = False,
) -> Iterator[TestClient]:
    class Cursor(psycopg.Cursor):
        def execute(self, query: object, params: object = None, **kwargs: object) -> Cursor:
            if fail_audit and "select record_audit_event" in str(query):
                return super().execute("select 1/0")
            return super().execute(query, params, **kwargs)

    @contextmanager
    def connect(*args: object, **kwargs: object) -> Iterator[psycopg.Connection]:
        with conn.transaction():
            yield conn

    with monkeypatch.context() as patch:
        patch.setattr(conn, "cursor_factory", Cursor)
        patch.setattr(module.db, "connect", connect)
        patch.setattr(
            module,
            "authenticated_client",
            lambda *_: PsycopgSupabaseClient(
                conn,
                claims=ws.claims(),
                honor_select=True,
            ),
        )
        patch.setattr(module, "enqueue_push_job", lambda *_: None)
        service = RequestsService()

        # Route any additional writer call through PostgreSQL so duplicates remain visible.
        class Writer:
            def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
                from psycopg.types.json import Jsonb

                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "select record_audit_event(%s,'success',%s,%s,%s,%s,%s)",
                        (
                            event.action,
                            ws.tenant_id,
                            ws.membership_id,
                            event.actor_email,
                            Jsonb(event.target),
                            event.trace_id,
                        ),
                    )

        patch.setattr(module, "get_audit_writer", lambda: Writer())
        if fail_response:

            def fail(*_: object) -> list[dict[str, object]]:
                raise RuntimeError("response read failed")

            patch.setattr(service, "_fetch_lines_for", fail)
        app = FastAPI()
        app.add_exception_handler(AppError, app_error_handler)
        app.include_router(router.router, prefix="/api/v1")
        app.dependency_overrides[current_member] = lambda: _current_member(ws, ws)
        app.dependency_overrides[bearer_token] = lambda: "token"
        app.dependency_overrides[get_requests_service] = lambda: service
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


def state(conn: psycopg.Connection, rid: UUID) -> tuple[object, list[object], list[object]]:
    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select r.status,s.status,s.comment from purchase_request r "
            "join approval_step s on s.purchase_request_id=r.id where r.id=%s",
            (rid,),
        )
        statuses = cur.fetchone()
        cur.execute(
            "select action,target from audit_event where target->>'purchase_request_id'=%s",
            (str(rid),),
        )
        audits = cur.fetchall()
        cur.execute("select id from push_notification where purchase_request_id=%s", (rid,))
        return statuses, audits, cur.fetchall()


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("comment", [" Decision reason ", "x" * 2000], ids=["padded", "limit"])
def test_decision_records_one_audit_and_retry_conflicts(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    comment: str,
) -> None:
    ws, rid, sid = seed(conn)
    with api_as(conn, monkeypatch, ws) as client:
        response = client.post(f"/api/v1/requests/{rid}/{action}", json={"comment": comment})
        assert response.status_code == 200, response.text
        retry = client.post(f"/api/v1/requests/{rid}/{action}", json={"comment": comment})
        assert retry.status_code == 409, retry.text
        assert retry.json()["details"] == {"reason": "not_submitted"}
    statuses, audits, notifications = state(conn, rid)
    decision = "approved" if action == "approve" else "rejected"
    assert statuses == ("ordered" if action == "approve" else "rejected", decision, comment)
    assert audits == [
        (
            f"requests.approval_step_{decision}",
            {
                "purchase_request_id": str(rid),
                "approval_step_id": str(sid),
                "decided_by_membership_id": str(ws.membership_id),
                "comment": comment,
                "self_approved": True,
            },
        )
    ]
    assert len(notifications) == 1


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_audit_failure_rolls_back_decision_and_outbox(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    ws, rid, _ = seed(conn)
    with api_as(conn, monkeypatch, ws, fail_audit=True) as client:
        response = client.post(f"/api/v1/requests/{rid}/{action}", json={"comment": "Reason"})
        assert response.status_code == 503, response.text
        assert response.json()["details"] == {"dependency": "database"}
    assert state(conn, rid) == (("submitted", "pending", None), [], [])


@pytest.mark.parametrize("comment", [None, "", "  \t\n"])
def test_reject_without_reason_writes_nothing(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    comment: str | None,
) -> None:
    ws, rid, _ = seed(conn)
    with api_as(conn, monkeypatch, ws) as client:
        response = client.post(f"/api/v1/requests/{rid}/reject", json={"comment": comment})
        assert response.status_code == 422, response.text
        assert response.json()["details"] == {"reason": "comment_required"}
    assert state(conn, rid) == (("submitted", "pending", None), [], [])


def test_cross_tenant_request_read_is_not_found(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, rid, _ = seed(conn)
    with conn.cursor() as cur:
        stranger = make_workspace(cur, "single-decision-other")
    with api_as(conn, monkeypatch, stranger) as client:
        for path in (f"/api/v1/requests/{rid}", f"/api/v1/requests/{rid}/approve"):
            response = client.get(path) if path.endswith(str(rid)) else client.post(path, json={})
            assert response.status_code == 404, response.text
    assert state(conn, rid) == (("submitted", "pending", None), [], [])


def test_response_read_failure_leaves_committed_decision_audited(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws, rid, _ = seed(conn)
    with api_as(conn, monkeypatch, ws, fail_response=True) as client:
        response = client.post(f"/api/v1/requests/{rid}/approve", json={})
        assert response.status_code == 500, response.text
    statuses, audits, notifications = state(conn, rid)
    assert statuses == ("ordered", "approved", None)
    assert len(audits) == len(notifications) == 1
    assert "comment" not in audits[0][1]
