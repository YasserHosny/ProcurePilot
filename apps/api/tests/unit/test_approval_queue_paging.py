from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from unit.test_approval_decisions import SelectQuery, member, request_row, step_row

from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as module


class PagingQuery(SelectQuery):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__(list(rows))
        self.orders: list[tuple[str, bool]] = []

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
        return response


class PagingClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.queries: list[PagingQuery] = []

    def table(self, _name: str) -> PagingQuery:
        query = PagingQuery(self.rows)
        self.queries.append(query)
        return query


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
