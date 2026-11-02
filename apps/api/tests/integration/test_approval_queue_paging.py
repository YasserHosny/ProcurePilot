"""P-170: queue traversal remains stable while approvals leave or enter the queue."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, make_workspace
from integration.smart_compare_helpers import member_from_workspace
from integration.test_approvals import (
    _make_branch,
    _make_pending_step,
    _make_submitted_request,
    _queue_service,
)
from procurepilot_api import db

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    # All fixture rows and decisions are rolled back, including on assertion failure.
    with db.connect(TEST_DATABASE_URL or "") as connection:
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.mark.parametrize("mutation", ["decision", "submission"])
@pytest.mark.parametrize("tied", [False, True])
def test_queue_traversal_survives_mutation(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, mutation: str, tied: bool
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "paging-owner")
        other = make_workspace(cur, "paging-foreign")
        act_as(cur, other)
        foreign_branch = _make_branch(cur, other)
        foreign = _make_submitted_request(cur, other, foreign_branch)
        _make_pending_step(cur, other.tenant_id, foreign, other.membership_id)
        act_as(cur, owner)
        branch = _make_branch(cur, owner)
        expected: list[UUID] = []
        for index in range(7):
            request = _make_submitted_request(cur, owner, branch)
            step = _make_pending_step(cur, owner.tenant_id, request, owner.membership_id)
            cur.execute(
                "update approval_step set created_at="
                "'2026-10-01T12:00:00.123456Z'::timestamptz + "
                "%s * interval '1 microsecond' where id=%s",
                (0 if tied else index, step),
            )
            expected.append(request)
    service = _queue_service(conn, monkeypatch, owner)
    member = member_from_workspace(owner)
    first = service.list_pending_approvals(bearer_token="test", member=member, limit=2)
    assert len(first.items) == 2
    assert first.next_cursor is not None
    with conn.cursor() as cur:
        if mutation == "decision":
            decided = first.items[0].id
            cur.execute(
                "update approval_step set status='approved', decided_at=now(), "
                "decided_by_membership_id=%s where purchase_request_id=%s",
                (owner.membership_id, decided),
            )
            cur.execute("update purchase_request set status='approved' where id=%s", (decided,))
        else:
            new = _make_submitted_request(cur, owner, branch)
            step = _make_pending_step(cur, owner.tenant_id, new, owner.membership_id)
            cur.execute(
                "update approval_step set created_at='2026-10-02T00:00:00Z' where id=%s", (step,)
            )
    seen = [item.id for item in first.items]
    cursor = first.next_cursor
    while cursor is not None:
        page = service.list_pending_approvals(
            bearer_token="test", member=member, limit=2, cursor=cursor
        )
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        assert len(seen) <= len(expected), "queue returned duplicate rows"
    assert len(seen) == len(set(seen))
    assert set(seen) == set(expected)
    assert foreign not in seen
    if mutation == "submission":
        refreshed = service.list_pending_approvals(bearer_token="test", member=member, limit=2)
        assert refreshed.items[0].id == new
