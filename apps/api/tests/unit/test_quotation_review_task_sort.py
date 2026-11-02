from __future__ import annotations

from types import SimpleNamespace
from typing import Literal
from uuid import UUID

import pytest
from postgrest import SyncPostgrestClient

from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.service import QuotationService


class FakeQuery:
    def __init__(self) -> None:
        self.filters: list[tuple[str, str, object]] = []
        self.orders: list[tuple[str, bool]] = []
        self.columns: str | None = None
        self.or_filters: list[str] = []
        self.range_args: tuple[int, int] | None = None
        self.limit_count: int | None = None
        self.data: list[dict[str, object]] = []
        self.executed = False

    def select(self, columns: str) -> FakeQuery:
        self.columns = columns
        return self

    def filter(self, column: str, operator: str, value: object) -> FakeQuery:
        self.filters.append((operator, column, value))
        return self

    def or_(self, filters: str) -> FakeQuery:
        self.or_filters.append(filters)
        return self

    def ilike(self, column: str, value: object) -> FakeQuery:
        return self.filter(column, "ilike", value)

    def in_(self, column: str, values: list[object]) -> FakeQuery:
        return self.filter(column, "in", values)

    def gte(self, column: str, value: object) -> FakeQuery:
        return self.filter(column, "gte", value)

    def lte(self, column: str, value: object) -> FakeQuery:
        return self.filter(column, "lte", value)

    def lt(self, column: str, value: object) -> FakeQuery:
        return self.filter(column, "lt", value)

    def limit(self, count: int) -> FakeQuery:
        self.limit_count = count
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self.orders.append((column, desc))
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self.range_args = (start, end)
        return self

    def execute(self) -> SimpleNamespace:
        self.executed = True
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self) -> None:
        self.review_task_query = FakeQuery()
        self.quotation_query = FakeQuery()
        self.tables: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.tables.append(name)
        if name == "quotation":
            return self.quotation_query
        assert name == "review_task"
        return self.review_task_query


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(
        quotation_service_module, "authenticated_client", lambda _settings, _token: client
    )
    monkeypatch.setattr(
        quotation_service_module,
        "_sync_open_review_tasks",
        lambda _client, _threshold: None,
    )
    return client


@pytest.mark.parametrize(
    "sort_order, expected_order",
    [
        ("asc", "quotation(stated_total_amount).asc,id"),
        ("desc", "quotation(stated_total_amount).desc.nullslast,id"),
    ],
)
def test_stated_total_orders_parent_tasks_by_quotation_amount(
    client: FakeClient, sort_order: Literal["asc", "desc"], expected_order: str
) -> None:
    QuotationService().list_review_tasks(
        bearer_token="dummy", sort_by="stated_total", sort_order=sort_order
    )

    orders = client.review_task_query.orders
    with SyncPostgrestClient("http://x/rest/v1") as postgrest:
        query = postgrest.table("review_task").select(client.review_task_query.columns or "")
        for column, descending in orders:
            query = query.order(column, desc=descending)
        assert query.params["order"] == expected_order
    assert all(column != "stated_total" for column, _ in orders)
    assert orders[-1] == ("id", False)


@pytest.mark.parametrize("sort_by", ["created_at", "priority", "status"])
@pytest.mark.parametrize("sort_order, descending", [("asc", False), ("desc", True)])
def test_plain_columns_keep_their_ordering(
    client: FakeClient,
    sort_by: Literal["created_at", "priority", "status"],
    sort_order: Literal["asc", "desc"],
    descending: bool,
) -> None:
    QuotationService().list_review_tasks(
        bearer_token="dummy", sort_by=sort_by, sort_order=sort_order
    )

    assert client.review_task_query.orders == [(sort_by, descending), ("id", False)]


@pytest.mark.parametrize("status", ["all", "resolved", None])
def test_status_filter_preserves_all_resolved_and_default_open(
    client: FakeClient, status: str | None
) -> None:
    service = QuotationService()
    if status is None:
        service.list_review_tasks(bearer_token="dummy")
    else:
        service.list_review_tasks(bearer_token="dummy", status=status)

    filters = client.review_task_query.filters
    if status == "all":
        assert all(column != "status" for _, column, _ in filters)
    else:
        assert ("eq", "status", status or "open") in filters


SUPPLIER_QUOTATION_ID = "12345678-1234-1234-1234-123456789abc"


def test_list_uses_inner_quotation_and_database_archive_filter(client: FakeClient) -> None:
    QuotationService().list_review_tasks(bearer_token="dummy")

    assert client.review_task_query.columns == (
        "id,quotation_id,status,priority,reason,created_at,resolved_at,"
        "quotation!inner(deleted_at,stated_total_amount,stated_total_currency,"
        "supplier!quotation_supplier_id_fkey(name))"
    )
    assert ("is", "quotation.deleted_at", "null") in client.review_task_query.filters
    assert "quotation!inner" not in quotation_service_module.TASK_COLUMNS


def test_supplier_search_looks_up_quotations_before_filtering_tasks(client: FakeClient) -> None:
    client.quotation_query.data = [{"id": SUPPLIER_QUOTATION_ID}]

    QuotationService().list_review_tasks(bearer_token="dummy", search="  FRESH  ")

    assert client.tables == ["quotation", "review_task"]
    assert client.quotation_query.columns == "id,supplier!quotation_supplier_id_fkey!inner(name)"
    assert client.quotation_query.filters == [("ilike", "supplier.name", "*fresh*")]
    assert client.quotation_query.limit_count == 150
    assert client.quotation_query.executed
    assert client.review_task_query.or_filters == [f"quotation_id.in.({SUPPLIER_QUOTATION_ID})"]


@pytest.mark.parametrize("supplier_match", [False, True])
@pytest.mark.parametrize(
    "prefix",
    ["c4cf2e80", "c", "c4cf2e80-1234", "c4cf2e80-1234-5678-9abc-def012345678"],
)
def test_uuid_prefix_search_uses_range_in_same_or(
    client: FakeClient, supplier_match: bool, prefix: str
) -> None:
    if supplier_match:
        client.quotation_query.data = [{"id": SUPPLIER_QUOTATION_ID}]

    QuotationService().list_review_tasks(bearer_token="dummy", search=prefix.upper())

    hex_prefix = prefix.replace("-", "")
    lo = str(UUID(hex=hex_prefix.ljust(32, "0")))
    hi = str(UUID(hex=hex_prefix.ljust(32, "f")))
    expected = f"and(quotation_id.gte.{lo},quotation_id.lte.{hi})"
    if supplier_match:
        expected = f"quotation_id.in.({SUPPLIER_QUOTATION_ID}),{expected}"
    assert client.review_task_query.or_filters == [expected]


@pytest.mark.parametrize("term", ["no such supplier", "g123", "a" * 33, ",()", "---"])
def test_unmatched_search_returns_empty_without_listing_tasks(
    client: FakeClient, term: str
) -> None:
    result = QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert result.items == []
    assert result.next_cursor is None
    assert not client.review_task_query.executed
    assert "review_task" not in client.tables


@pytest.mark.parametrize("term", [",()", "( , )"])
def test_search_stripped_to_empty_never_looks_up_all_suppliers(
    client: FakeClient, term: str
) -> None:
    client.quotation_query.data = [{"id": SUPPLIER_QUOTATION_ID}]

    result = QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert result.items == []
    assert result.next_cursor is None
    assert not client.quotation_query.executed
    assert not client.review_task_query.executed


@pytest.mark.parametrize(
    "term, escaped",
    [
        (r"fresh\%_ supplier,(x)", r"fresh\\\%\_ supplierx"),
        ("x" * 201, "x" * 200),
        ("*", r"\*"),
    ],
)
def test_supplier_search_escapes_pattern_and_keeps_term_out_of_or(
    client: FakeClient, term: str, escaped: str
) -> None:
    client.quotation_query.data = [{"id": SUPPLIER_QUOTATION_ID}]

    QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert client.quotation_query.filters == [("ilike", "supplier.name", f"*{escaped}*")]
    assert client.review_task_query.or_filters == [f"quotation_id.in.({SUPPLIER_QUOTATION_ID})"]


def test_database_page_is_not_filtered_again_in_python(client: FakeClient) -> None:
    client.quotation_query.data = [{"id": SUPPLIER_QUOTATION_ID}]
    # Deliberately inconsistent embeds: the fake returns a database-filtered page.
    # Neither archive nor search checks should discard its rows after pagination.
    client.review_task_query.data = [
        {
            "id": f"00000000-0000-0000-0000-{i:012d}",
            "quotation_id": SUPPLIER_QUOTATION_ID,
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": "2026-02-28T12:00:00Z",
            "quotation": {"deleted_at": "2026-02-28T13:00:00Z"},
        }
        for i in range(1, 4)
    ]

    result = QuotationService().list_review_tasks(bearer_token="dummy", search="fresh", limit=2)

    assert len(result.items) == 2
    assert result.next_cursor == quotation_service_module._encode_cursor(2)
    assert client.review_task_query.range_args == (0, 2)

    QuotationService().list_review_tasks(bearer_token="dummy", cursor=result.next_cursor, limit=2)
    assert client.review_task_query.range_args == (2, 4)


@pytest.mark.parametrize(
    "date_to, operator, expected",
    [
        ("2026-02-28", "lt", "2026-03-01T00:00:00+00:00"),
        ("2024-02-28", "lt", "2024-02-29T00:00:00+00:00"),
        ("2024-02-29", "lt", "2024-03-01T00:00:00+00:00"),
        ("2026-12-31", "lt", "2027-01-01T00:00:00+00:00"),
        ("2026-02-28T23:59:59Z", "lte", "2026-02-28T23:59:59Z"),
        ("2026-02-30", "lte", "2026-02-30"),
        ("invalid", "lte", "invalid"),
        ("9999-12-31", "lte", "9999-12-31"),
    ],
)
def test_date_to_bounds_and_date_from_unchanged(
    client: FakeClient, date_to: str, operator: str, expected: str
) -> None:
    QuotationService().list_review_tasks(
        bearer_token="dummy", date_from="2026-01-01", date_to=date_to
    )

    assert (operator, "created_at", expected) in client.review_task_query.filters
    assert ("gte", "created_at", "2026-01-01") in client.review_task_query.filters
    assert len([f for f in client.review_task_query.filters if f[0] in {"lt", "lte"}]) == 1
