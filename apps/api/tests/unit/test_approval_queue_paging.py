from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    PsycopgTableQuery,
    _plain_select_columns,
)
from psycopg import sql
from unit.test_approval_decisions import SelectQuery, member, request_row, step_row

from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import router as requests_router
from procurepilot_api.modules.requests import service as module


class PagingQuery(SelectQuery):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__(list(rows))
        self.orders: list[tuple[str, bool]] = []
        self.columns = ["*"]

    def select(self, columns: str) -> PagingQuery:
        self.columns = _plain_select_columns(columns)
        return self

    def order(self, column: str, *, desc: bool = False) -> PagingQuery:
        self.orders.append((column, desc))
        return self

    def or_(self, expression: str) -> PagingQuery:
        match = re.fullmatch(
            r"created_at.lt.([^,]+),and\(created_at.eq.([^,]+),id.gt.([^)]+)\)", expression
        )
        assert match is not None
        timestamp, same_timestamp, step_id = match.groups()
        assert timestamp == same_timestamp
        boundary = datetime.fromisoformat(timestamp.strip('"'))
        self.rows = [
            row
            for row in self.rows
            if datetime.fromisoformat(str(row["created_at"])) < boundary
            or (
                datetime.fromisoformat(str(row["created_at"])) == boundary
                and str(row["id"]) > step_id
            )
        ]
        return self

    def execute(self) -> SimpleNamespace:
        for column, desc in reversed(self.orders):
            self.rows.sort(key=lambda row: str(row[column]), reverse=desc)
        response = super().execute()
        response.data = response.data[:1000]  # Data API's max_rows
        if "*" not in self.columns:
            response.data = [
                {key: value for key, value in row.items() if key in self.columns}
                for row in response.data
            ]
        return response


class PagingClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[PagingQuery] = []

    def table(self, _name: str) -> PagingQuery:
        query = PagingQuery(self.rows)
        self.queries.append(query)
        return query


@pytest.mark.asyncio
async def test_pending_first_page_returns_200_and_cursor_from_selected_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = member(role=MemberRole.owner)
    timestamp = "2026-10-01T12:00:00.123456+00:00"
    steps = [{**step_row(uuid4(), owner.membership_id), "created_at": timestamp} for _ in range(3)]
    client = PagingClient(steps)
    service = module.RequestsService()
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(
        service,
        "_fetch_requests_batch",
        lambda _client, ids: [request_row(UUID(rid), owner.membership_id) for rid in ids],
    )
    for method in (
        "_fetch_lines_batch",
        "_fetch_member_contacts_batch",
        "_fetch_auto_prepared_batch",
        "_fetch_sources_batch",
        "_fetch_request_groups_batch",
    ):
        monkeypatch.setattr(service, method, lambda *_: {})
    monkeypatch.setattr(
        service,
        "_purchase_request_with_budget_status",
        lambda _client, row, lines, step, **_: module._purchase_request(row, lines, step),
    )
    app = FastAPI()
    app.include_router(requests_router.router, prefix="/api/v1")
    app.dependency_overrides[requests_router.bearer_token] = lambda: "test"
    app.dependency_overrides[requests_router.current_member] = lambda: owner
    app.dependency_overrides[requests_router.get_requests_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/api/v1/approvals/pending?limit=2")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["next_cursor"] is not None
    last_step_id = UUID(payload["items"][-1]["approval_step"]["id"])
    assert module._decode_approval_cursor(payload["next_cursor"]) == (
        "2026-10-01T12:00:00.123456Z",
        last_step_id,
    )
    assert "created_at" in client.queries[0].columns


def test_paging_double_omits_unselected_columns_and_ignores_embed() -> None:
    rows = [{"id": "step", "created_at": "timestamp", "status": "pending"}]
    query = PagingQuery(rows).select("id,purchase_request!inner(status)")
    assert query.execute().data == [{"id": "step"}]


@pytest.mark.parametrize(
    "columns,projection",
    [
        ("id,purchase_request!inner(status)", '"id"'),
        ("id,created_at,purchase_request!inner(status)", '"id","created_at"'),
        ("id,quotation(status,supplier(id,name)),created_at", '"id","created_at"'),
        ("*,purchase_request!inner(status)", "*"),
    ],
)
def test_sql_adapter_selects_only_requested_plain_columns(
    monkeypatch: pytest.MonkeyPatch, columns: str, projection: str
) -> None:
    query = PsycopgSupabaseClient(Mock(spec=psycopg.Connection), honor_select=True).table(
        "approval_step"
    )
    statements: list[str] = []

    def fetch(statement: sql.SQL, _params: list[object]) -> list[dict[str, object]]:
        statements.append(statement.as_string())
        return []

    monkeypatch.setattr(query, "_fetch", fetch)
    query.select(columns).execute()
    assert statements == [f'select {projection} from "approval_step"']


@pytest.mark.parametrize("via_client", [False, True])
def test_sql_adapter_default_preserves_select_star(
    monkeypatch: pytest.MonkeyPatch, via_client: bool
) -> None:
    connection = Mock(spec=psycopg.Connection)
    query = (
        PsycopgSupabaseClient(connection).table("approval_step")
        if via_client
        else PsycopgTableQuery(connection, "approval_step")
    )
    statements: list[str] = []

    def fetch(statement: sql.SQL, _params: list[object]) -> list[dict[str, object]]:
        statements.append(statement.as_string())
        return []

    monkeypatch.setattr(query, "_fetch", fetch)
    query.select("id,alias:column,value::text,metadata->>name,quotation(status)").execute()
    assert statements == ['select * from "approval_step"']


def test_approval_cursor_round_trip_preserves_microseconds() -> None:
    step_id = uuid4()
    cursor = module._encode_approval_cursor("2026-10-01T14:00:00.123456+02:00", step_id)
    assert module._decode_approval_cursor(cursor) == ("2026-10-01T12:00:00.123456Z", step_id)
    assert module._decode_approval_cursor(None) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"offset": 2},
        {"created_at": "bad", "id": str(uuid4())},
        {"created_at": "2026-10-01", "id": str(uuid4())},
        {"created_at": "2026-10-01T00:00:00Z", "id": "bad"},
    ],
)
def test_invalid_approval_cursor(payload: object) -> None:
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(UnprocessableEntityError) as exc:
        module._decode_approval_cursor(cursor)
    assert exc.value.details == {"cursor": "invalid"}


@pytest.mark.parametrize("cursor", ["!", "é", "e30=garbage"])
def test_malformed_approval_cursor(cursor: str) -> None:
    with pytest.raises(UnprocessableEntityError) as exc:
        module._decode_approval_cursor(cursor)
    assert exc.value.details == {"cursor": "invalid"}


@pytest.mark.parametrize("tied", [False, True])
@pytest.mark.parametrize("mutation", ["none", "decision", "submission"])
def test_second_page_starts_strictly_after_last_step(
    monkeypatch: pytest.MonkeyPatch, tied: bool, mutation: str
) -> None:
    owner = member(role=MemberRole.owner)
    steps = [
        {
            **step_row(uuid4(), owner.membership_id),
            "id": UUID(int=index + 1),
            "created_at": f"2026-10-01T12:00:00.{123456 if tied else 123459 - index:06d}+00:00",
        }
        for index in range(4)
    ]
    client = PagingClient(steps)
    service = module.RequestsService()
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(
        service,
        "_fetch_requests_batch",
        lambda _client, ids: [request_row(UUID(rid), owner.membership_id) for rid in ids],
    )
    for method in (
        "_fetch_lines_batch",
        "_fetch_member_contacts_batch",
        "_fetch_auto_prepared_batch",
        "_fetch_sources_batch",
        "_fetch_request_groups_batch",
    ):
        monkeypatch.setattr(service, method, lambda *_: {})
    monkeypatch.setattr(
        service,
        "_purchase_request_with_budget_status",
        lambda _client, row, lines, step, **_: module._purchase_request(row, lines, step),
    )
    first = service.list_pending_approvals(bearer_token="test", member=owner, limit=2)
    assert first.next_cursor is not None
    if mutation == "decision":
        client.rows = steps[1:]
    elif mutation == "submission":
        client.rows = [
            {**step_row(uuid4(), owner.membership_id), "created_at": "2026-10-02T00:00:00Z"},
            *steps,
        ]
    second = service.list_pending_approvals(
        bearer_token="test", member=owner, limit=2, cursor=first.next_cursor
    )
    assert [item.id for item in first.items + second.items] == [
        s["purchase_request_id"] for s in steps
    ]
    assert second.next_cursor is None
    assert module._decode_approval_cursor(first.next_cursor)[1] == steps[1]["id"]


@pytest.mark.parametrize("limit,expected_end", [(None, 50), (1000, 100), (0, 1)])
def test_pending_queue_limit_semantics(
    monkeypatch: pytest.MonkeyPatch, limit: int | None, expected_end: int
) -> None:
    client = PagingClient([])
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    service = module.RequestsService()
    owner = member(role=MemberRole.owner)
    if limit is None:
        result = service.list_pending_approvals(bearer_token="test", member=owner)
    else:
        result = service.list_pending_approvals(bearer_token="test", member=owner, limit=limit)
    assert result.items == []
    assert result.next_cursor is None
    assert client.queries[0].ranges == [(0, expected_end)]


def test_pending_queue_malformed_cursor_uses_existing_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "authenticated_client", lambda *_: PagingClient([]))
    with pytest.raises(UnprocessableEntityError) as exc:
        module.RequestsService().list_pending_approvals(
            bearer_token="test", member=member(), cursor="!"
        )
    assert exc.value.details == {"cursor": "invalid"}


@pytest.mark.parametrize("count", [1003, 2000])
def test_line_batch_fetches_every_data_api_page(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    request_ids = [str(uuid4()), str(uuid4())]
    product_id = str(uuid4())
    rows = [
        {
            "id": str(UUID(int=i + 1)),
            "purchase_request_id": request_ids[i % 2],
            "workspace_product_id": product_id,
            "position": i,
            "created_at": "2026-10-01",
        }
        for i in range(count)
    ]
    client = PagingClient(rows)
    service = module.RequestsService()
    lookups: list[list[str]] = []

    def details(_client: object, ids: list[str]) -> dict[str, dict[str, str]]:
        lookups.append(ids)
        return {product_id: {"product_name": "Product", "base_unit": "kg"}}

    monkeypatch.setattr(service, "_fetch_product_details_batch", details)
    result = service._fetch_lines_batch(client, request_ids)
    fetched = [line for lines in result.values() for line in lines]
    assert len(fetched) == count
    assert {line["id"] for line in fetched} == {row["id"] for row in rows}
    assert all(line["product_name"] == "Product" for line in fetched)
    assert lookups == [[product_id]]
    assert [query.ranges for query in client.queries] == [
        [(start, start + 999)] for start in range(0, count + 1, 1000)
    ]


@pytest.fixture(autouse=True)
def sql_queue_double(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the existing hydration tests focused on the page returned by the SQL layer."""

    def page(
        self: object, *, member: object, sort: str, branch_id: object, boundary: object, limit: int
    ) -> tuple[list[dict], int]:
        client = module.authenticated_client(None, None)
        query = client.table("approval_step").select("*,created_at")
        total = len(query.rows)
        if boundary is not None:
            value, step_id = boundary
            query.or_(f"created_at.lt.{value},and(created_at.eq.{value},id.gt.{step_id})")
        rows = query.order("created_at", desc=True).order("id").range(0, limit).execute().data
        return [{**row, "sort_value": row["created_at"]} for row in rows], total

    monkeypatch.setattr(module.RequestsService, "_pending_approval_page", page)
