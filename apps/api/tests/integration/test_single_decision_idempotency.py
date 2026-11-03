"""Decision replay through HTTP, RLS and concurrent database transactions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    delete_tenant_scoped_rows,
    make_workspace,
    reset_role,
)
from integration.test_approvals import _make_member
from integration.test_purchase_requests import _current_member
from integration.test_single_decision_audit import api_as, seed, state
from integration.test_single_decision_audit import conn as conn
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_keyed_decision_replays_once(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    ws, rid, _ = seed(conn)
    headers = {"Idempotency-Key": str(uuid4())}
    with api_as(conn, monkeypatch, ws) as client:
        first = client.post(
            f"/api/v1/requests/{rid}/{action}", headers=headers, json={"comment": "Reason"}
        )
        assert first.status_code == 200, first.text
        replay = client.post(
            f"/api/v1/requests/{rid}/{action}", headers=headers, json={"comment": " " * 2001}
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == first.json()
    _, audits, pushes = state(conn, rid)
    assert len(audits) == len(pushes) == 1
    assert audits[0][1]["idempotency_key"] == headers["Idempotency-Key"]


@pytest.mark.parametrize(
    "retry", ["no_key", "different_key", "opposite", "owner", "requester", "tenant"]
)
def test_key_does_not_bypass_scope_or_conflicts(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, retry: str
) -> None:
    ws, rid, _ = seed(conn)
    with conn.cursor() as cur:
        assigned = _make_member(cur, ws.tenant_id, f"approver-{uuid4().hex}", "approver")
        cur.execute(
            "update approval_step set assigned_membership_id=%s where purchase_request_id=%s",
            (assigned.membership_id, rid),
        )
        other_owner = _make_member(cur, ws.tenant_id, f"owner-{uuid4().hex}", "owner")
        requester = _make_member(cur, ws.tenant_id, f"buyer-{uuid4().hex}", "buyer")
        cur.execute(
            "update purchase_request set requested_by_membership_id=%s where id=%s",
            (requester.membership_id, rid),
        )
        stranger = make_workspace(cur, "decision-key-other")
    headers = {"Idempotency-Key": str(uuid4())}
    with api_as(conn, monkeypatch, assigned) as client:
        first = client.post(f"/api/v1/requests/{rid}/approve", headers=headers, json={})
        assert first.status_code == 200, first.text
    actor = (
        other_owner
        if retry == "owner"
        else requester
        if retry == "requester"
        else stranger
        if retry == "tenant"
        else assigned
    )
    retry_headers = (
        {}
        if retry == "no_key"
        else {"Idempotency-Key": str(uuid4())}
        if retry == "different_key"
        else headers
    )
    action = "reject" if retry == "opposite" else "approve"
    with api_as(conn, monkeypatch, actor) as client:
        response = client.post(
            f"/api/v1/requests/{rid}/{action}", headers=retry_headers, json={"comment": "Reason"}
        )
        assert response.status_code == (
            404 if retry == "tenant" else 403 if retry == "requester" else 409
        ), response.text
    _, audits, pushes = state(conn, rid)
    assert len(audits) == len(pushes) == 1


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_concurrent_keyed_decisions_have_one_audit_and_outbox(decision: str) -> None:
    # Separate connections require committed setup; teardown targets only this generated tenant.
    with module.db.connect(TEST_DATABASE_URL) as setup:
        ws, rid, sid = seed(setup)
        with setup.cursor() as cur:
            cur.execute("select platform_invitation_id from tenant where id=%s", (ws.tenant_id,))
            invitation_id = cur.fetchone()[0]
    key = uuid4()
    barrier = Barrier(2)

    def decide() -> tuple[dict, dict, object] | int:
        barrier.wait(timeout=15)
        try:
            return RequestsService()._decide_and_notify(
                member=_current_member(ws, ws),
                request_id=str(rid),
                step_id=str(sid),
                decision=decision,
                comment="Reason",
                now=module._now_iso(),
                idempotency_key=key,
            )
        except ConflictError as exc:
            return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: decide(), range(2)))
        successes = [result for result in results if isinstance(result, tuple)]
        assert len(successes) >= 1
        assert all(isinstance(result, tuple) or result == 409 for result in results)
        assert sum(result[2] is not None for result in successes) == 1
        with module.db.connect(TEST_DATABASE_URL) as check:
            statuses, audits, pushes = state(check, rid)
            assert statuses[:2] == ("ordered" if decision == "approved" else "rejected", decision)
            assert len(audits) == len(pushes) == 1
    finally:
        with module.db.connect(TEST_DATABASE_URL) as cleanup, cleanup.cursor() as cur:
            reset_role(cur)
            delete_tenant_scoped_rows(cur, ws.tenant_id)
            cur.execute("delete from tenant where id=%s", (ws.tenant_id,))
            cur.execute("delete from auth.users where id=%s", (ws.user_id,))
            cur.execute("delete from platform_invitation where id=%s", (invitation_id,))
