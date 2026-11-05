from __future__ import annotations

from collections.abc import Iterator
from typing import Literal
from uuid import UUID

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_quotation,
    make_review_task,
    make_supplier,
)
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.service import QuotationService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


@pytest.fixture
def workspace(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "review-list-filters")
        act_as(cur, workspace)
    monkeypatch.setattr(
        quotation_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(conn),
    )
    return workspace


def _task(
    conn: psycopg.Connection, workspace: Workspace, supplier_id: UUID | None = None
) -> tuple[UUID, UUID]:
    with conn.cursor() as cur:
        quotation_id = make_quotation(cur, workspace, supplier_id=supplier_id)
        task_id = make_review_task(cur, workspace, quotation_id, reason="line_count_mismatch")
    return quotation_id, task_id


def test_archived_quotation_does_not_consume_page_space(
    conn: psycopg.Connection, workspace: Workspace
) -> None:
    archived, _ = _task(conn, workspace)
    visible = [_task(conn, workspace)[1] for _ in range(2)]
    with conn.cursor() as cur:
        cur.execute("update quotation set deleted_at=now() where id=%s", (archived,))
    result = QuotationService().list_review_tasks(bearer_token="test-token", limit=2)
    assert {task.id for task in result.items} == set(visible)
    assert result.next_cursor is None


@pytest.mark.parametrize("name", ["Later Supplier", "Acme (UK), Ltd"])
def test_supplier_search_filters_before_pagination(
    conn: psycopg.Connection, workspace: Workspace, name: str
) -> None:
    with conn.cursor() as cur:
        supplier = make_supplier(cur, workspace, name)
    quotation_id, target = _task(conn, workspace, supplier)
    with conn.cursor() as cur:
        cur.execute(
            "update review_task set created_at='2026-01-01T00:00:00Z' where id=%s", (target,)
        )
    for _ in range(3):
        _task(conn, workspace)
    service = QuotationService()
    unfiltered = service.list_review_tasks(bearer_token="test-token", limit=2)
    assert target not in {task.id for task in unfiltered.items}
    result = service.list_review_tasks(bearer_token="test-token", search=name, limit=2)
    assert [task.quotation_id for task in result.items] == [quotation_id]
    assert result.next_cursor is None


def test_eight_hex_id_prefix_matches_only_its_quotation(
    conn: psycopg.Connection, workspace: Workspace
) -> None:
    quotation_id, target = _task(conn, workspace)
    _task(conn, workspace)
    result = QuotationService().list_review_tasks(
        bearer_token="test-token", search=quotation_id.hex[:8]
    )
    assert [task.id for task in result.items] == [target]
    assert result.next_cursor is None


def test_unmatched_search_returns_empty(conn: psycopg.Connection, workspace: Workspace) -> None:
    _task(conn, workspace)
    result = QuotationService().list_review_tasks(
        bearer_token="test-token", search="No such supplier"
    )
    assert result.items == []
    assert result.next_cursor is None


def test_supplier_with_160_quotations_paginates_all_tasks(
    conn: psycopg.Connection, workspace: Workspace
) -> None:
    with conn.cursor() as cur:
        supplier = make_supplier(cur, workspace, "Bulk Supplier")
        # Keep the real service and RLS active while avoiding 160 fixture round trips.
        cur.execute(
            "with documents as ("
            "insert into document "
            "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
            "select gen_random_uuid(),%s,'quotation-documents',"
            "'tenants/' || %s || '/quotations/bulk/' || n,'application/pdf','bulk-' || n,%s "
            "from generate_series(1,160) n returning id,tenant_id"
            "), quotations as ("
            "insert into quotation (id,tenant_id,document_id,supplier_id,status,currency) "
            "select gen_random_uuid(),tenant_id,id,%s,'pending','GBP' from documents "
            "returning id,tenant_id) "
            "insert into review_task (id,tenant_id,quotation_id,reason,priority) "
            "select gen_random_uuid(),tenant_id,id,'line_count_mismatch','normal' from quotations "
            "returning id",
            (workspace.tenant_id, str(workspace.tenant_id), workspace.membership_id, supplier),
        )
        expected = {row[0] for row in cur.fetchall()}
    service = QuotationService()
    first = service.list_review_tasks(bearer_token="test-token", search="Bulk Supplier", limit=100)
    assert len(first.items) == 100
    assert first.next_cursor is not None
    second = service.list_review_tasks(
        bearer_token="test-token", search="Bulk Supplier", limit=100, cursor=first.next_cursor
    )
    assert len(second.items) == 60
    assert second.next_cursor is None
    assert {task.id for task in first.items}.isdisjoint(task.id for task in second.items)
    assert {task.id for task in first.items + second.items} == expected


def test_bare_date_to_includes_entire_day(conn: psycopg.Connection, workspace: Workspace) -> None:
    _, same_day = _task(conn, workspace)
    _, next_day = _task(conn, workspace)
    with conn.cursor() as cur:
        cur.execute(
            "update review_task set created_at='2026-02-28T23:59:59.999999Z' where id=%s",
            (same_day,),
        )
        cur.execute(
            "update review_task set created_at='2026-03-01T00:00:00Z' where id=%s", (next_day,)
        )
    result = QuotationService().list_review_tasks(bearer_token="test-token", date_to="2026-02-28")
    assert [task.id for task in result.items] == [same_day]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_stated_total_sort_keeps_nulls_last(
    conn: psycopg.Connection, workspace: Workspace, direction: Literal["asc", "desc"]
) -> None:
    expected = []
    # Insertion order differs from either amount order; null is inserted between amounts.
    for amount in [20, None, 3, 100]:
        quotation_id, task_id = _task(conn, workspace)
        with conn.cursor() as cur:
            cur.execute(
                "update quotation set stated_total_amount=%s,stated_total_currency=%s where id=%s",
                (amount, "GBP" if amount is not None else None, quotation_id),
            )
        expected.append(task_id)
    result = QuotationService().list_review_tasks(
        bearer_token="test-token", sort_by="stated_total", sort_order=direction
    )
    indices = [2, 0, 3, 1] if direction == "asc" else [3, 0, 2, 1]
    assert [task.id for task in result.items] == [expected[i] for i in indices]


def test_status_all_includes_open_and_resolved(
    conn: psycopg.Connection, workspace: Workspace
) -> None:
    _, open_task = _task(conn, workspace)
    _, resolved_task = _task(conn, workspace)
    with conn.cursor() as cur:
        cur.execute(
            "update review_task set status='resolved',resolved_at=now() where id=%s",
            (resolved_task,),
        )
    service = QuotationService()
    assert [task.id for task in service.list_review_tasks(bearer_token="test-token").items] == [
        open_task
    ]
    result = service.list_review_tasks(bearer_token="test-token", status="all")
    assert {task.id: task.status for task in result.items} == {
        open_task: "open",
        resolved_task: "resolved",
    }


@pytest.mark.parametrize("method", ["eq", "in_", "is_", "filter_eq", "filter_in", "filter_is"])
def test_adapter_embedded_filters_are_correlated(
    conn: psycopg.Connection, workspace: Workspace, method: str
) -> None:
    quotation_id, target = _task(conn, workspace)
    other, _ = _task(conn, workspace)
    with conn.cursor() as cur:
        cur.execute("update quotation set deleted_at=now() where id=%s", (other,))
    query = PsycopgSupabaseClient(conn).table("review_task").select()
    if method == "eq":
        query = query.eq("quotation.id", quotation_id)
    elif method == "in_":
        query = query.in_("quotation.id", [quotation_id])
    elif method == "is_":
        query = query.is_("quotation.deleted_at", "null")
    elif method == "filter_eq":
        query = query.filter("quotation.id", "eq", quotation_id)
    elif method == "filter_in":
        query = query.filter("quotation.id", "in", [quotation_id])
    else:
        query = query.filter("quotation.deleted_at", "is", "null")
    assert [row["id"] for row in query.execute().data] == [target]


@pytest.mark.parametrize("pattern", ["*a*b*", "%a%b%", r"*a\*b*", r"%a\*b%"])
def test_adapter_ilike_preserves_escaped_asterisks_and_sql_wildcards(
    conn: psycopg.Connection, workspace: Workspace, pattern: str
) -> None:
    with conn.cursor() as cur:
        literal = make_supplier(cur, workspace, "A*B")
        wildcard = make_supplier(cur, workspace, "AxxB")
    rows = PsycopgSupabaseClient(conn).table("supplier").select().ilike("name", pattern).execute()
    expected = {literal} if r"\*" in pattern else {literal, wildcard}
    assert {row["id"] for row in rows.data} == expected


@pytest.mark.parametrize(
    "term,descending,null_first",
    [
        ("quotation(stated_total_amount)", True, True),
        ("quotation(stated_total_amount).asc.nullsfirst", False, True),
        ("quotation(stated_total_amount).desc.nullslast", False, False),
        ("quotation(stated_total_amount).nullslast", True, False),
    ],
)
def test_adapter_embedded_order_options(
    conn: psycopg.Connection,
    workspace: Workspace,
    term: str,
    descending: bool,
    null_first: bool,
) -> None:
    quotation_id, amount_task = _task(conn, workspace)
    _, null_task = _task(conn, workspace)
    with conn.cursor() as cur:
        cur.execute(
            "update quotation set stated_total_amount=10,stated_total_currency='GBP' where id=%s",
            (quotation_id,),
        )
    rows = (
        PsycopgSupabaseClient(conn)
        .table("review_task")
        .select()
        .order(term, desc=descending)
        .execute()
    )
    expected = [null_task, amount_task] if null_first else [amount_task, null_task]
    assert [row["id"] for row in rows.data] == expected


@pytest.mark.parametrize("ordering", [False, True])
def test_adapter_rejects_unknown_embeds(
    conn: psycopg.Connection, workspace: Workspace, ordering: bool
) -> None:
    query = PsycopgSupabaseClient(conn).table("review_task").select()
    query = query.order("unknown(id)") if ordering else query.eq("unknown.id", workspace.tenant_id)
    with pytest.raises(NotImplementedError, match="unknown embed"):
        query.execute()


@pytest.mark.parametrize("filter_name", ["supplier_id", "reason", "quotation_status", "combined"])
def test_queue_filters_narrow_before_pagination(
    conn: psycopg.Connection, workspace: Workspace, filter_name: str
) -> None:
    with conn.cursor() as cur:
        supplier = make_supplier(cur, workspace, "Selected Supplier")
        other_supplier = make_supplier(cur, workspace, "Other Supplier")
    quotation_id, target = _task(conn, workspace, supplier)
    _task(conn, workspace, other_supplier)
    _, other_task = _task(conn, workspace, supplier)
    with conn.cursor() as cur:
        cur.execute("update quotation set status='in_review' where id=%s", (quotation_id,))
        cur.execute("update review_task set reason='total_unverified' where id=%s", (other_task,))
    service = QuotationService()
    if filter_name == "supplier_id":
        result = service.list_review_tasks(bearer_token="test-token", supplier_id=supplier)
        assert {task.id for task in result.items} == {target, other_task}
    elif filter_name == "reason":
        result = service.list_review_tasks(bearer_token="test-token", reason="total_unverified")
        assert [task.id for task in result.items] == [other_task]
    elif filter_name == "quotation_status":
        result = service.list_review_tasks(bearer_token="test-token", quotation_status="in_review")
        assert [task.id for task in result.items] == [target]
    else:
        result = service.list_review_tasks(
            bearer_token="test-token",
            supplier_id=supplier,
            reason="line_count_mismatch",
            quotation_status="in_review",
            search="Selected",
            status="open",
            limit=1,
        )
        assert [task.id for task in result.items] == [target]
        assert result.next_cursor is None
        assert (
            service.list_review_tasks(
                bearer_token="test-token", supplier_id=other_supplier, search="Selected"
            ).items
            == []
        )


def test_other_tenant_supplier_filter_returns_empty(
    conn: psycopg.Connection, workspace: Workspace
) -> None:
    _task(conn, workspace)
    with conn.cursor() as cur:
        other = make_workspace(cur, "other-queue-filter")
        act_as(cur, other)
        supplier = make_supplier(cur, other, "Other Tenant Supplier")
    _task(conn, other, supplier)
    with conn.cursor() as cur:
        act_as(cur, workspace)
    result = QuotationService().list_review_tasks(bearer_token="test-token", supplier_id=supplier)
    assert result.items == []
    assert result.next_cursor is None
