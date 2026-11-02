from __future__ import annotations

from types import SimpleNamespace
from typing import Literal

import pytest
from postgrest import SyncPostgrestClient

from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.service import QuotationService


class FakeQuery:
    def __init__(self) -> None:
        self.filters: list[tuple[str, str, object]] = []
        self.orders: list[tuple[str, bool]] = []

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self.orders.append((column, desc))
        return self

    def range(self, _start: int, _end: int) -> FakeQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[])


class FakeClient:
    def __init__(self) -> None:
        self.review_task_query = FakeQuery()

    def table(self, name: str) -> FakeQuery:
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
        query = postgrest.table("review_task").select("id")
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
