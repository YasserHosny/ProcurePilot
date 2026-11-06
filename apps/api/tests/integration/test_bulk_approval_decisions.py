"""Bulk HTTP decisions retain per-request RLS, transactions, audit and replay."""

from __future__ import annotations

from uuid import UUID, uuid4, uuid5

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace, reset_role
from integration.test_approvals import (
    _make_branch,
    _make_member,
    _make_pending_step,
    _make_submitted_request,
)
from integration.test_single_decision_audit import api_as, state
from integration.test_single_decision_audit import conn as conn

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


def seed_batch(connection: psycopg.Connection, count: int = 3) -> tuple[Workspace, list[UUID]]:
    with connection.cursor() as cur:
        reset_role(cur)
        owner = make_workspace(cur, f"bulk-{uuid4().hex}")
        requester = _make_member(cur, owner.tenant_id, f"buyer-{uuid4().hex}", "buyer")
        branch = _make_branch(cur, owner)
        ids = []
        for _ in range(count):
            rid = _make_submitted_request(cur, requester, branch)
            _make_pending_step(cur, owner.tenant_id, rid, owner.membership_id)
            ids.append(rid)
    return owner, ids


def test_three_owner_decisions_each_have_one_audit_and_replay_writes_nothing(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, ids = seed_batch(conn)
    key = uuid4()
    body = {"decision": "approved", "request_ids": [str(rid) for rid in ids]}
    with api_as(conn, monkeypatch, owner) as client:
        first = client.post(
            "/api/v1/approvals/bulk-decisions", json=body, headers={"Idempotency-Key": str(key)}
        )
        assert first.status_code == 200, first.text
        result = first.json()
        assert result["decided_count"] == 3 and result["failed_count"] == 0
        assert [item["request_id"] for item in result["results"]] == body["request_ids"]
        assert all(
            item["outcome"] == "decided" and item["request"]["status"] == "approved"
            for item in result["results"]
        )
        replay = client.post(
            "/api/v1/approvals/bulk-decisions", json=body, headers={"Idempotency-Key": str(key)}
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == result
    for rid in ids:
        statuses, audits, pushes = state(conn, rid)
        assert statuses == ("approved", "approved", None)
        assert len(audits) == len(pushes) == 1
        assert audits[0][0] == "requests.approval_step_approved"
        assert audits[0][1]["idempotency_key"] == str(uuid5(key, str(rid)))


def test_mixed_batch_preserves_self_decision_and_tenant_checks_and_continues(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, ids = seed_batch(conn)
    good, already, self_submitted = ids
    with conn.cursor() as cur:
        reset_role(cur)
        other_owner = _make_member(cur, owner.tenant_id, f"owner-{uuid4().hex}", "owner")
        cur.execute(
            "update purchase_request set requested_by_membership_id=%s where id=%s",
            (owner.membership_id, self_submitted),
        )
    _, foreign_ids = seed_batch(conn, count=1)
    foreign = foreign_ids[0]
    with api_as(conn, monkeypatch, other_owner) as client:
        decided = client.post(f"/api/v1/requests/{already}/approve", json={})
        assert decided.status_code == 200, decided.text
    ordered = [already, self_submitted, foreign, good]
    body = {"decision": "approved", "request_ids": [str(rid) for rid in ordered]}
    key = str(uuid4())
    with api_as(conn, monkeypatch, owner) as client:
        response = client.post(
            "/api/v1/approvals/bulk-decisions", json=body, headers={"Idempotency-Key": key}
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["decided_count"] == 1 and result["failed_count"] == 3
        assert [item["request_id"] for item in result["results"]] == body["request_ids"]
        assert [item["error_code"] for item in result["results"]] == [
            "conflict",
            "self_decision_not_allowed",
            "not_found",
            None,
        ]
        assert all(item["request"] is None for item in result["results"][:3])
        replay = client.post(
            "/api/v1/approvals/bulk-decisions", json=body, headers={"Idempotency-Key": key}
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == result
    for rid in [already, good]:
        statuses, audits, pushes = state(conn, rid)
        assert statuses[:2] == ("approved", "approved")
        assert len(audits) == len(pushes) == 1
    for rid in [self_submitted, foreign]:
        assert state(conn, rid) == (("submitted", "pending", None), [], [])


def test_response_failure_is_per_item_and_replay_recovers_committed_decisions(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, ids = seed_batch(conn)
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"decision": "approved", "request_ids": [str(rid) for rid in ids]}
    with api_as(conn, monkeypatch, owner, fail_response=True) as client:
        response = client.post("/api/v1/approvals/bulk-decisions", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["failed_count"] == 3
        assert [item["error_code"] for item in response.json()["results"]] == ["unavailable"] * 3
    with api_as(conn, monkeypatch, owner) as client:
        replay = client.post("/api/v1/approvals/bulk-decisions", json=body, headers=headers)
        assert replay.status_code == 200, replay.text
        assert replay.json()["decided_count"] == 3
    for rid in ids:
        statuses, audits, pushes = state(conn, rid)
        assert statuses[:2] == ("approved", "approved")
        assert len(audits) == len(pushes) == 1
