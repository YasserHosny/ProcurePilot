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
        data = self.data
        if self.limit_count is not None:
            data = data[: self.limit_count]
        if self.range_args is not None:
            start, end = self.range_args
            data = data[start : end + 1]
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self) -> None:
        self.review_task_query = FakeQuery()
        self.quotation_query = FakeQuery()
        self.supplier_query = FakeQuery()
        self.tables: list[str] = []

    def table(self, name: str) -> FakeQuery:
        self.tables.append(name)
        if name == "supplier":
            return self.supplier_query
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


def test_list_uses_inner_quotation_and_database_archive_filter(client: FakeClient) -> None:
    QuotationService().list_review_tasks(bearer_token="dummy")

    assert client.review_task_query.columns == (
        "id,quotation_id,status,priority,reason,created_at,resolved_at,"
        "quotation!inner(deleted_at,stated_total_amount,stated_total_currency,"
        "supplier!quotation_supplier_id_fkey(name))"
    )
    assert ("is", "quotation.deleted_at", "null") in client.review_task_query.filters
    assert "quotation!inner" not in quotation_service_module.TASK_COLUMNS


SUPPLIER_IDS = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]


def test_supplier_search_filters_embedded_supplier_without_quotation_lookup(
    client: FakeClient,
) -> None:
    client.supplier_query.data = [{"id": supplier_id} for supplier_id in SUPPLIER_IDS]

    QuotationService().list_review_tasks(bearer_token="dummy", search="  FRESH  ")

    assert client.tables == ["supplier", "review_task"]
    assert client.supplier_query.columns == "id"
    assert client.supplier_query.filters == [("ilike", "name", "*fresh*")]
    assert client.supplier_query.orders == [("name", False)]
    assert client.supplier_query.limit_count == 500
    assert client.supplier_query.executed
    assert ("in", "quotation.supplier_id", SUPPLIER_IDS) in client.review_task_query.filters
    assert client.review_task_query.or_filters == []
    assert "quotation" not in client.tables


@pytest.mark.parametrize(
    "prefix",
    ["c4cf2e80", "c", "c4cf2e80-1234", "c4cf2e80-1234-5678-9abc-def012345678"],
)
def test_uuid_prefix_without_supplier_uses_id_range(client: FakeClient, prefix: str) -> None:
    QuotationService().list_review_tasks(bearer_token="dummy", search=prefix.upper())

    hex_prefix = prefix.replace("-", "")
    lo = str(UUID(hex=hex_prefix.ljust(32, "0")))
    hi = str(UUID(hex=hex_prefix.ljust(32, "f")))
    assert ("gte", "quotation_id", lo) in client.review_task_query.filters
    assert ("lte", "quotation_id", hi) in client.review_task_query.filters
    assert all(operator != "in" for operator, _, _ in client.review_task_query.filters)
    assert client.review_task_query.or_filters == []
    assert client.tables == ["supplier", "review_task"]


def test_hex_supplier_match_takes_precedence_over_id_range(client: FakeClient) -> None:
    client.supplier_query.data = [{"id": SUPPLIER_IDS[0]}]

    QuotationService().list_review_tasks(bearer_token="dummy", search="ace")

    assert ("in", "quotation.supplier_id", SUPPLIER_IDS[:1]) in client.review_task_query.filters
    assert all(column != "quotation_id" for _, column, _ in client.review_task_query.filters)
    assert client.review_task_query.or_filters == []
    assert client.tables == ["supplier", "review_task"]


@pytest.mark.parametrize("term", ["no such supplier", "g123", "a" * 33, "---"])
def test_unmatched_search_returns_empty_without_listing_tasks(
    client: FakeClient, term: str
) -> None:
    result = QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert result.items == []
    assert result.next_cursor is None
    assert client.tables == ["supplier"]
    assert client.supplier_query.executed
    assert not client.review_task_query.executed


@pytest.mark.parametrize(
    "term, pattern",
    [("Acme (UK)", "*acme (uk)*"), ("Smith, Jones", "*smith, jones*")],
)
def test_supplier_search_preserves_name_punctuation(
    client: FakeClient, term: str, pattern: str
) -> None:
    client.supplier_query.data = [{"id": SUPPLIER_IDS[0]}]

    QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert client.supplier_query.filters == [("ilike", "name", pattern)]
    assert client.supplier_query.executed
    assert ("in", "quotation.supplier_id", SUPPLIER_IDS[:1]) in client.review_task_query.filters


@pytest.mark.parametrize("term", ["()", ",()", "( , )"])
def test_unmatched_punctuation_search_returns_empty(client: FakeClient, term: str) -> None:
    result = QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert client.supplier_query.filters == [("ilike", "name", f"*{term}*")]
    assert client.supplier_query.executed
    assert result.items == []
    assert result.next_cursor is None
    assert client.tables == ["supplier"]
    assert not client.review_task_query.executed


@pytest.mark.parametrize("term", ["   ", "", None])
def test_search_cleaned_to_empty_lists_tasks_without_search_filter(
    client: FakeClient, term: str | None
) -> None:
    QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert client.tables == ["review_task"]
    assert not client.supplier_query.executed
    assert client.review_task_query.executed
    assert client.review_task_query.or_filters == []
    assert all(
        column not in {"quotation.supplier_id", "quotation_id"}
        for _, column, _ in client.review_task_query.filters
    )


@pytest.mark.parametrize(
    "term, escaped",
    [
        (r"fresh\%_ supplier,(x)", r"fresh\\\%\_ supplier,(x)"),
        ("x" * 201, "x" * 200),
        ("*", r"\*"),
    ],
)
def test_supplier_search_escapes_pattern_and_keeps_term_out_of_or(
    client: FakeClient, term: str, escaped: str
) -> None:
    client.supplier_query.data = [{"id": SUPPLIER_IDS[0]}]

    QuotationService().list_review_tasks(bearer_token="dummy", search=term)

    assert client.supplier_query.filters == [("ilike", "name", f"*{escaped}*")]
    assert client.review_task_query.or_filters == []
    assert ("in", "quotation.supplier_id", SUPPLIER_IDS[:1]) in client.review_task_query.filters
    assert "quotation" not in client.tables


def test_supplier_with_400_quotations_keeps_all_tasks_and_pagination(client: FakeClient) -> None:
    client.supplier_query.data = [{"id": SUPPLIER_IDS[0]}]
    # Deliberately inconsistent embeds: database-filtered rows must survive pagination.
    # Each task belongs to a distinct quotation from the same supplier.
    client.review_task_query.data = [
        {
            "id": str(UUID(int=i)),
            "quotation_id": str(UUID(int=1000 + i)),
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": "2026-02-28T12:00:00Z",
            "quotation": {"deleted_at": "2026-02-28T13:00:00Z"},
        }
        for i in range(1, 401)
    ]

    service = QuotationService()
    cursor = None
    seen: list[UUID] = []
    for page in range(4):
        result = service.list_review_tasks(
            bearer_token="dummy", search="fresh", limit=100, cursor=cursor
        )
        assert len(result.items) == 100
        assert client.review_task_query.range_args == (page * 100, (page + 1) * 100)
        cursor = result.next_cursor
        assert cursor == (
            quotation_service_module._encode_cursor((page + 1) * 100) if page < 3 else None
        )
        seen.extend(item.id for item in result.items)

    assert seen == [UUID(int=i) for i in range(1, 401)]
    assert ("in", "quotation.supplier_id", SUPPLIER_IDS[:1]) in client.review_task_query.filters
    assert client.review_task_query.or_filters == []
    assert client.review_task_query.limit_count is None
    assert "quotation" not in client.tables
    assert client.quotation_query.limit_count is None
    assert not client.quotation_query.executed


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
