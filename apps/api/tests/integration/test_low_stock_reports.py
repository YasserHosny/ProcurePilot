"""Low-stock report integration tests — T029 (009-mobile-app-mvp, US3).

Proves at the database level: report rows can be created with or without a
count, branch-scoped visibility matches purchase_request's shape, low-stock
reporting leaves purchase_request untouched (FR-006), and the partial unique
index enforces idempotent replay keys (FR-011).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with R2.2 migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


@dataclass(frozen=True)
class LowStockWorkspace:
    owner: Workspace
    scoped_manager: Workspace
    branch_a: UUID
    branch_b: UUID
    product_id: UUID
    report_a: UUID
    report_b_own: UUID
    report_b_other: UUID


def _make_member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Workspace:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}@example.test"),
    )
    cur.execute(
        "insert into membership "
        "(id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def _make_branch(cur: psycopg.Cursor, workspace: Workspace, name: str) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, name),
    )
    return branch_id


def _make_low_stock_report(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    product_id: UUID,
    *,
    member_id: UUID | None = None,
    count_remaining: str | None = None,
    idempotency_key: UUID | None = None,
) -> UUID:
    report_id = uuid4()
    cur.execute(
        "insert into low_stock_report "
        "(id,tenant_id,branch_id,member_id,workspace_product_id,"
        " count_remaining,idempotency_key) "
        "values (%s,%s,%s,%s,%s,%s,%s)",
        (
            report_id,
            workspace.tenant_id,
            branch_id,
            member_id or workspace.membership_id,
            product_id,
            count_remaining,
            idempotency_key,
        ),
    )
    return report_id


def _make_request(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    *,
    status: str = "draft",
) -> UUID:
    request_id = uuid4()
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,"
        " required_by_date,status) "
        "values (%s,%s,%s,%s,current_date + interval '7 days',%s)",
        (
            request_id,
            workspace.tenant_id,
            branch_id,
            workspace.membership_id,
            status,
        ),
    )
    return request_id


def _snapshot_purchase_requests(cur: psycopg.Cursor, tenant_id: UUID) -> list[tuple]:
    cur.execute(
        "select * from purchase_request where tenant_id = %s order by id",
        (tenant_id,),
    )
    return cur.fetchall()


def _make_visibility_workspace(cur: psycopg.Cursor, label: str) -> LowStockWorkspace:
    owner = make_workspace(cur, label)
    scoped_manager = _make_member(cur, owner.tenant_id, f"{label}-scoped", "branch_manager")
    other_manager = _make_member(cur, owner.tenant_id, f"{label}-other", "branch_manager")

    branch_a = _make_branch(cur, owner, "Branch A")
    branch_b = _make_branch(cur, owner, "Branch B")
    cur.execute(
        "insert into branch_role_assignment "
        "(id,tenant_id,membership_id,branch_id) "
        "values (%s,%s,%s,%s)",
        (uuid4(), owner.tenant_id, scoped_manager.membership_id, branch_a),
    )

    product_id = make_workspace_product(cur, owner, name=f"{label} Widget")
    act_as(cur, owner)
    report_a = _make_low_stock_report(
        cur,
        owner,
        branch_a,
        product_id,
        member_id=other_manager.membership_id,
    )
    report_b_own = _make_low_stock_report(
        cur,
        owner,
        branch_b,
        product_id,
        member_id=scoped_manager.membership_id,
    )
    report_b_other = _make_low_stock_report(
        cur,
        owner,
        branch_b,
        product_id,
        member_id=other_manager.membership_id,
    )

    return LowStockWorkspace(
        owner=owner,
        scoped_manager=scoped_manager,
        branch_a=branch_a,
        branch_b=branch_b,
        product_id=product_id,
        report_a=report_a,
        report_b_own=report_b_own,
        report_b_other=report_b_other,
    )


def test_low_stock_report_creation_accepts_count_remaining(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "lsr-create-count")
        branch_id = _make_branch(cur, ws, "Main")
        product_id = make_workspace_product(cur, ws, name="Milk")
        act_as(cur, ws)
        report_id = _make_low_stock_report(
            cur, ws, branch_id, product_id, count_remaining="7.250000"
        )

        cur.execute(
            "select branch_id, member_id, workspace_product_id,"
            " count_remaining::text "
            "from low_stock_report where id = %s",
            (report_id,),
        )
        assert cur.fetchone() == (
            branch_id,
            ws.membership_id,
            product_id,
            "7.250000",
        )


def test_low_stock_report_creation_accepts_omitted_count_remaining(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "lsr-create-no-count")
        branch_id = _make_branch(cur, ws, "Main")
        product_id = make_workspace_product(cur, ws, name="Bread")
        act_as(cur, ws)
        report_id = _make_low_stock_report(cur, ws, branch_id, product_id)

        cur.execute(
            "select count_remaining from low_stock_report where id = %s",
            (report_id,),
        )
        assert cur.fetchone() == (None,)


def test_branch_scoped_member_sees_assigned_branch_and_own_reports(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        scoped = _make_visibility_workspace(cur, "lsr-visibility")

        act_as(cur, scoped.scoped_manager)
        cur.execute("select id from low_stock_report order by id")
        assert [row[0] for row in cur.fetchall()] == sorted([scoped.report_a, scoped.report_b_own])

        cur.execute(
            "select id from low_stock_report where id = %s",
            (scoped.report_b_other,),
        )
        assert cur.fetchone() is None


def test_owner_sees_every_low_stock_report(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        scoped = _make_visibility_workspace(cur, "lsr-owner")

        act_as(cur, scoped.owner)
        cur.execute("select id from low_stock_report order by id")
        assert [row[0] for row in cur.fetchall()] == sorted(
            [scoped.report_a, scoped.report_b_own, scoped.report_b_other]
        )


def test_low_stock_report_does_not_mutate_purchase_requests(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "lsr-fr006")
        branch_id = _make_branch(cur, ws, "Main")
        product_id = make_workspace_product(cur, ws, name="Coffee")
        act_as(cur, ws)
        _make_request(cur, ws, branch_id)
        _make_request(cur, ws, branch_id, status="submitted")

        before = _snapshot_purchase_requests(cur, ws.tenant_id)
        _make_low_stock_report(cur, ws, branch_id, product_id, count_remaining="2.000000")
        after = _snapshot_purchase_requests(cur, ws.tenant_id)

        assert after == before


def test_idempotency_key_is_unique_per_tenant(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "lsr-idempotency-key")
        branch_id = _make_branch(cur, ws, "Main")
        product_id = make_workspace_product(cur, ws, name="Tea")
        act_as(cur, ws)
        key = uuid4()
        _make_low_stock_report(
            cur,
            ws,
            branch_id,
            product_id,
            count_remaining="4.000000",
            idempotency_key=key,
        )

        cur.execute("savepoint duplicate_low_stock_report_key")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _make_low_stock_report(
                cur,
                ws,
                branch_id,
                product_id,
                count_remaining="5.000000",
                idempotency_key=key,
            )
        cur.execute("rollback to savepoint duplicate_low_stock_report_key")

        cur.execute(
            "select count(*) from low_stock_report where tenant_id = %s and idempotency_key = %s",
            (ws.tenant_id, key),
        )
        assert cur.fetchone() == (1,)


def test_omitted_idempotency_key_reports_are_not_deduped(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "lsr-no-idempotency-key")
        branch_id = _make_branch(cur, ws, "Main")
        product_id = make_workspace_product(cur, ws, name="Water")
        act_as(cur, ws)
        first = _make_low_stock_report(cur, ws, branch_id, product_id)
        second = _make_low_stock_report(cur, ws, branch_id, product_id)

        cur.execute(
            "select id from low_stock_report where tenant_id = %s and id in (%s,%s)",
            (ws.tenant_id, first, second),
        )
        assert {row[0] for row in cur.fetchall()} == {first, second}
