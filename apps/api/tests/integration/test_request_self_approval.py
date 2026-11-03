"""ADR-024 routing, decision authorization and audit marks through HTTP and real RLS.

The shared connection fixture rolls back all generated tenant data, including audit events.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.test_approvals import _make_branch, _make_member
from integration.test_purchase_requests import _add_line_no_estimate, _make_request
from integration.test_request_group_schema import _insert_group, _setup
from integration.test_single_decision_audit import api_as, seed, state
from integration.test_single_decision_audit import conn as conn

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("keyed", [False, True])
@pytest.mark.parametrize("legacy_assignment", [False, True])
def test_two_owners_refuse_requester_decision(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    keyed: bool,
    legacy_assignment: bool,
) -> None:
    ws, rid, _ = seed(conn)
    with conn.cursor() as cur:
        reset_role(cur)
        other = _make_member(cur, ws.tenant_id, f"owner-{uuid4().hex}", "owner")
        if not legacy_assignment:
            cur.execute(
                "update approval_step set assigned_membership_id=%s where purchase_request_id=%s",
                (other.membership_id, rid),
            )
    headers = {"Idempotency-Key": str(uuid4())} if keyed else {}
    with api_as(conn, monkeypatch, ws) as client:
        response = client.post(
            f"/api/v1/requests/{rid}/{action}", headers=headers, json={"comment": "Decision reason"}
        )
        assert response.status_code == 403, response.text
        assert response.json()["details"] == {"reason": "self_decision_not_allowed"}
    statuses, audits, pushes = state(conn, rid)
    assert statuses[:2] == ("submitted", "pending")
    assert audits == pushes == []
    with api_as(conn, monkeypatch, other) as client:
        response = client.post(
            f"/api/v1/requests/{rid}/{action}", headers=headers, json={"comment": "Decision reason"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["approval_step"]["self_approval"] is False
    assert "self_approved" not in state(conn, rid)[1][0][1]


@pytest.mark.parametrize("two_owners", [False, True])
def test_owner_submission_and_sole_owner_mark(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    two_owners: bool,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, f"self-routing-{uuid4().hex}")
        other = (
            _make_member(cur, ws.tenant_id, f"owner-{uuid4().hex}", "owner") if two_owners else ws
        )
        branch = _make_branch(cur, ws)
        rid = _make_request(cur, ws, branch)
        product = make_workspace_product(cur, ws, name="Request product")
        _add_line_no_estimate(cur, ws, rid, product)
    with api_as(conn, monkeypatch, ws) as client:
        response = client.post(f"/api/v1/requests/{rid}/submit")
        assert response.status_code == 200, response.text
        step = response.json()["approval_step"]
        assert step["assigned_membership_id"] == str(other.membership_id)
        assert step["self_approval"] is (not two_owners)
        if two_owners:
            return
        for path in ("/api/v1/approvals/pending", "/api/v1/requests"):
            response = client.get(path)
            assert response.status_code == 200, response.text
            request = next(item for item in response.json()["items"] if item["id"] == str(rid))
            assert request["approval_step"]["self_approval"] is True
        response = client.post(f"/api/v1/requests/{rid}/approve", json={})
        assert response.status_code == 200, response.text
        assert response.json()["approval_step"]["self_approval"] is True
    audits = [row for row in state(conn, rid)[1] if row[0] == "requests.approval_step_approved"]
    assert audits[0][1]["self_approved"] is True


def test_matching_non_owner_requester_routes_to_owner(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, f"self-matching-{uuid4().hex}")
        requester = _make_member(cur, ws.tenant_id, f"approver-{uuid4().hex}", "approver")
        branch = _make_branch(cur, ws)
        rid = _make_request(cur, ws, branch, requested_by_membership_id=requester.membership_id)
        product = make_workspace_product(cur, ws, name="Request product")
        line = _add_line_no_estimate(cur, ws, rid, product)
        cur.execute(
            "update purchase_request_line set estimated_unit_price_amount=10, "
            "estimated_unit_price_currency='GBP' where id=%s",
            (line,),
        )
        cur.execute(
            "insert into threshold_rule "
            "(tenant_id,min_amount,currency,approver_membership_id,created_by) "
            "values (%s,0,'GBP',%s,%s)",
            (ws.tenant_id, requester.membership_id, ws.membership_id),
        )
    with api_as(conn, monkeypatch, requester) as client:
        response = client.post(f"/api/v1/requests/{rid}/submit")
        assert response.status_code == 200, response.text
        assert response.json()["approval_step"]["assigned_membership_id"] == str(ws.membership_id)
        assert response.json()["approval_step"]["source"] == "owner_fallback"


@contextmanager
def group_api_as(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    ws: Workspace,
) -> Iterator[TestClient]:
    # The group transaction requests a connection-level dict row factory; the shared
    # savepoint adapter returns this test connection rather than opening a new connection.
    previous_factory = conn.row_factory
    with api_as(conn, monkeypatch, ws) as client:
        conn.row_factory = dict_row
        try:
            yield client
        finally:
            conn.row_factory = previous_factory


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("two_owners", [False, True])
def test_split_requester_decisions(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    two_owners: bool,
) -> None:
    with conn.cursor() as cur:
        ws, branch, rfq, job = _setup(cur, f"self-group-{uuid4().hex}")
        other = (
            _make_member(cur, ws.tenant_id, f"owner-{uuid4().hex}", "owner") if two_owners else ws
        )
        group = _insert_group(cur, ws, branch, rfq, job)
        for amount in (2773, 1290):
            rid = _make_request(cur, ws, branch)
            cur.execute(
                "update purchase_request set request_group_id=%s, estimated_total_amount=%s, "
                "estimated_total_currency='SAR',has_incomplete_estimate=false where id=%s",
                (group, amount, rid),
            )
    base = f"/api/v1/request-groups/{group}"
    with group_api_as(conn, monkeypatch, ws) as client:
        response = client.post(f"{base}/submit", headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 200, response.text
        assert {r["approval_step"]["assigned_membership_id"] for r in response.json()} == {
            str(other.membership_id)
        }
        response = client.post(
            f"{base}/{action}",
            headers={"Idempotency-Key": str(uuid4())},
            json={"comment": "Decision reason"},
        )
        assert response.status_code == (403 if two_owners else 200), response.text
        if two_owners:
            assert response.json()["details"] == {"reason": "self_decision_not_allowed"}
        else:
            assert all(r["approval_step"]["self_approval"] for r in response.json())
    if two_owners:
        with group_api_as(conn, monkeypatch, other) as client:
            response = client.post(
                f"{base}/{action}",
                headers={"Idempotency-Key": str(uuid4())},
                json={"comment": "Decision reason"},
            )
            assert response.status_code == 200, response.text
            assert all(not r["approval_step"]["self_approval"] for r in response.json())
    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select target from audit_event where tenant_id=%s and action=%s",
            (ws.tenant_id, f"requests.group_{'approved' if action == 'approve' else 'rejected'}"),
        )
        target = cur.fetchone()[0]
        assert (target.get("self_approved") is True) is (not two_owners)
        if two_owners:
            assert "self_approved" not in target


def test_other_tenant_decision_remains_not_found(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, rid, _ = seed(conn)
    with conn.cursor() as cur:
        reset_role(cur)
        stranger = make_workspace(cur, f"self-stranger-{uuid4().hex}")
    with api_as(conn, monkeypatch, stranger) as client:
        for action in ("approve", "reject"):
            response = client.post(f"/api/v1/requests/{rid}/{action}", json={"comment": "Reason"})
            assert response.status_code == 404, response.text
