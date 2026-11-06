"""Sort/filter/count traversal using the authenticated role and real RLS."""

from datetime import UTC, date, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    execute_as_table_owner,
    make_workspace,
    reset_role,
)
from integration.smart_compare_helpers import member_from_workspace
from integration.test_approval_queue_paging import conn as conn
from integration.test_approvals import (
    _make_branch,
    _make_member,
    _make_pending_step,
    _make_submitted_request,
    _queue_service,
)
from procurepilot_api.modules.requests.schemas import RequestGroupSummary

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")
SORTS = ["submitted_desc", "submitted_asc", "required_by_asc", "total_desc", "total_asc"]


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("mutation", ["decision", "submission"])
def test_all_sorts_traverse_with_changes(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, sort: str, mutation: str
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, f"sort-owner-{uuid4().hex}")
        foreign = make_workspace(cur, f"sort-foreign-{uuid4().hex}")
        act_as(cur, foreign)
        foreign_branch = _make_branch(cur, foreign)
        foreign_id = _make_submitted_request(cur, foreign, foreign_branch)
        _make_pending_step(cur, foreign.tenant_id, foreign_id, foreign.membership_id)
        act_as(cur, owner)
        branch = _make_branch(cur, owner)
        original = []
        for index, amount in enumerate([20, None, 10, 20, None, 30, 10]):
            rid = _make_submitted_request(cur, owner, branch)
            sid = _make_pending_step(cur, owner.tenant_id, rid, owner.membership_id)
            stamp = datetime(2026, 10, 1, microsecond=index // 2, tzinfo=UTC)
            required = date(2026, 10, 1 + index // 2)
            execute_as_table_owner(
                cur, owner, "update approval_step set created_at=%s where id=%s", (stamp, sid)
            )
            cur.execute(
                "update purchase_request set required_by_date=%s, estimated_total_amount=%s, "
                "estimated_total_currency=%s where id=%s",
                (required, amount, "GBP" if amount is not None else None, rid),
            )
            value = (
                stamp
                if sort.startswith("submitted")
                else required
                if sort == "required_by_asc"
                else amount
            )
            original.append((rid, sid, value))
    # Independent stable sort: ID ascending within each value, nulls last.
    known = sorted(original, key=lambda row: row[1])
    non_null = sorted(
        [row for row in known if row[2] is not None],
        key=lambda row: row[2],
        reverse=sort.endswith("desc"),
    )
    expected = [row[0] for row in non_null + [row for row in known if row[2] is None]]
    service = _queue_service(conn, monkeypatch, owner)
    member = member_from_workspace(owner)
    first = service.list_pending_approvals(bearer_token="test", member=member, sort=sort, limit=2)
    assert first.total == 7
    assert [item.id for item in first.items] == expected[:2]
    if sort == "submitted_desc":
        default = service.list_pending_approvals(bearer_token="test", member=member, limit=2)
        assert [item.id for item in default.items] == expected[:2]
    with conn.cursor() as cur:
        if mutation == "decision":
            execute_as_table_owner(
                cur,
                owner,
                "update approval_step set status='approved', decided_at=now(), "
                "decided_by_membership_id=%s where purchase_request_id=%s",
                (owner.membership_id, first.items[0].id),
            )
            total = 6
        else:
            new = _make_submitted_request(cur, owner, branch)
            sid = _make_pending_step(cur, owner.tenant_id, new, owner.membership_id)
            execute_as_table_owner(
                cur,
                owner,
                "update approval_step set created_at=%s where id=%s",
                ("2030-01-01" if sort == "submitted_desc" else "2020-01-01", sid),
            )
            cur.execute(
                "update purchase_request set required_by_date='2020-01-01', "
                "estimated_total_amount=%s, estimated_total_currency='GBP' where id=%s",
                (999 if sort == "total_desc" else 0, new),
            )
            total = 8
    seen = [item.id for item in first.items]
    cursor = first.next_cursor
    while cursor:
        page = service.list_pending_approvals(
            bearer_token="test", member=member, sort=sort, limit=2, cursor=cursor
        )
        assert page.total == total
        seen.extend(item.id for item in page.items)
        assert len(seen) <= 7
        cursor = page.next_cursor
    assert seen == expected
    assert foreign_id not in seen
    empty = service.list_pending_approvals(
        bearer_token="test", member=member, sort=sort, branch_id=foreign_branch
    )
    assert empty.items == [] and empty.total == 0


@pytest.mark.parametrize("sort", SORTS)
def test_visibility_filters_and_count(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, sort: str
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, f"filter-owner-{uuid4().hex}")
        other = _make_member(cur, owner.tenant_id, f"filter-other-{uuid4().hex}", "owner")
        approver = _make_member(cur, owner.tenant_id, f"filter-approver-{uuid4().hex}", "approver")
        branch, another, hidden, empty_branch = [_make_branch(cur, owner) for _ in range(4)]
        cur.execute(
            "insert into branch_role_assignment (tenant_id, membership_id, branch_id) "
            "values (%s,%s,%s),(%s,%s,%s)",
            (
                owner.tenant_id,
                approver.membership_id,
                branch,
                owner.tenant_id,
                approver.membership_id,
                another,
            ),
        )
        expected = {branch: [], another: [], hidden: [], empty_branch: []}
        for target in (branch, another, hidden):
            for _ in range(3):
                rid = _make_submitted_request(cur, other, target)
                _make_pending_step(cur, owner.tenant_id, rid, approver.membership_id)
                expected[target].append(rid)
        own = _make_submitted_request(cur, owner, branch)
        _make_pending_step(cur, owner.tenant_id, own, other.membership_id)
        non_assigned = _make_submitted_request(cur, other, branch)
        _make_pending_step(cur, owner.tenant_id, non_assigned, other.membership_id)
        self_assigned = _make_submitted_request(cur, approver, branch)
        _make_pending_step(cur, owner.tenant_id, self_assigned, approver.membership_id)
        terminal = _make_submitted_request(cur, other, branch)
        _make_pending_step(cur, owner.tenant_id, terminal, approver.membership_id)
        cur.execute(
            "update purchase_request set status='withdrawn', withdrawn_at=now() where id=%s",
            (terminal,),
        )
    for actor in (owner, approver):
        service = _queue_service(conn, monkeypatch, actor)
        member = member_from_workspace(actor)
        for target in (branch, another, hidden, empty_branch, uuid4(), None):
            ids = set()
            for b, requests in expected.items():
                if (target is None or target == b) and (actor == owner or b != hidden):
                    ids.update(requests)
            if target in (None, branch):
                ids.update([non_assigned, self_assigned] if actor == owner else [])
            cursor = None
            seen = []
            while True:
                page = service.list_pending_approvals(
                    bearer_token="test",
                    member=member,
                    sort=sort,
                    branch_id=target,
                    limit=2,
                    cursor=cursor,
                )
                assert page.total == len(ids)
                seen.extend(item.id for item in page.items)
                cursor = page.next_cursor
                if cursor is None:
                    break
                assert len(seen) <= len(ids)
            assert set(seen) == ids
            assert len(seen) == len(ids)
            assert own not in seen and terminal not in seen
    with conn.cursor() as cur:
        reset_role(cur)


@pytest.mark.parametrize("sort", ["total_desc", "total_asc"])
@pytest.mark.parametrize("limit", [1, 2])
def test_split_group_combined_total_traversal(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, sort: str, limit: int
) -> None:
    from integration.test_request_group_schema import _insert_group, _setup

    with conn.cursor() as cur:
        owner, branch, rfq, job = _setup(cur, f"group-sort-{uuid4().hex}")
        group = _insert_group(cur, owner, branch, rfq, job)
        act_as(cur, owner)
        members = []
        ordinary = []
        # The immutable group total is 4063 SAR; member estimates deliberately differ.
        for amount, grouped in [(1, True), (2, True), (50, False), (100, False)]:
            rid = _make_submitted_request(cur, owner, branch)
            sid = _make_pending_step(cur, owner.tenant_id, rid, owner.membership_id)
            cur.execute(
                "update purchase_request set estimated_total_amount=%s, "
                "estimated_total_currency='SAR', request_group_id=%s where id=%s",
                (amount, group if grouped else None, rid),
            )
            (members if grouped else ordinary).append((rid, sid))
    group_ids = [rid for rid, _ in sorted(members, key=lambda row: row[1])]
    expected = (
        group_ids + [rid for rid, _ in reversed(ordinary)]
        if sort == "total_desc"
        else [rid for rid, _ in ordinary] + group_ids
    )
    service = _queue_service(conn, monkeypatch, owner)
    member = member_from_workspace(owner)

    # The shared adapter cannot embed PostgREST relations. Use the equivalent real-RLS
    # SQL enrichment so page-edge assertions include every sibling outside the page.
    def fetch_groups(
        _client: object, rows: list[dict[str, object]]
    ) -> dict[str, RequestGroupSummary]:
        previous_row_factory = conn.row_factory
        try:
            conn.row_factory = dict_row
            return service._fetch_request_groups_sql(conn, member=member, request_rows=rows)
        finally:
            conn.row_factory = previous_row_factory

    monkeypatch.setattr(service, "_fetch_request_groups_batch", fetch_groups)
    seen = []
    cursor = None
    while True:
        page = service.list_pending_approvals(
            bearer_token="test", member=member, sort=sort, limit=limit, cursor=cursor
        )
        assert page.total == 4
        seen.extend(item.id for item in page.items)
        assert seen == expected[: len(seen)]
        assert len(seen) <= 4
        for item in page.items:
            if item.id in group_ids:
                assert item.request_group is not None
                assert item.request_group.size == 2
                assert set(item.request_group.sibling_request_ids) == set(group_ids) - {item.id}
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == expected
