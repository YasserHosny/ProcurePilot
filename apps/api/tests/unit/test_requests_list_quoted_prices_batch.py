"""Listing RFQ-sourced requests must not open a database connection per row.

Each connection to the hosted pooler costs a TLS handshake plus a query round trip, so a
per-row connect made a 34-request list take over five seconds (PPS-227, in-app feedback 2026-11-22).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.requests import service as service_module
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import QuotedPrice

type Quotes = dict[tuple[str, str], QuotedPrice]


def _listing(
    monkeypatch: pytest.MonkeyPatch, *, sourced: int, manual: int
) -> tuple[RequestsService, Mock, Quotes]:
    service = RequestsService()
    branch, member = uuid4(), uuid4()
    rows: list[dict[str, object]] = []
    lines_by_request: dict[str, list[dict[str, object]]] = {}
    quotes: Quotes = {}
    for i in range(sourced + manual):
        request_id, product_id = str(uuid4()), str(uuid4())
        response_id = str(uuid4()) if i < sourced else None
        rows.append(
            {
                "id": request_id,
                "branch_id": str(branch),
                "requested_by_membership_id": str(member),
                "required_by_date": "2026-11-30",
                "status": "draft",
                "estimated_total_amount": "10",
                "estimated_total_currency": "SAR",
                "created_at": "2026-11-01T00:00:00Z",
                "source_rfq_response_id": response_id,
            }
        )
        lines_by_request[request_id] = [
            {"id": str(uuid4()), "workspace_product_id": product_id, "quantity": "1"}
        ]
        if response_id:
            quotes[(response_id, product_id)] = QuotedPrice(Decimal(i + 1), "SAR", False, None)

    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = lambda: SimpleNamespace(data=rows)
    monkeypatch.setattr(service_module, "authenticated_client", lambda *_: client)
    for name in (
        "_fetch_steps_batch",
        "_fetch_member_contacts_batch",
        "_fetch_auto_prepared_batch",
        "_fetch_sources_batch",
        "_fetch_request_groups_batch",
    ):
        monkeypatch.setattr(service, name, Mock(return_value={}))
    monkeypatch.setattr(service, "_fetch_lines_batch", Mock(return_value=lines_by_request))
    monkeypatch.setattr(service, "_fetch_budget_rows", Mock(return_value=[]))

    connects = Mock()

    @contextmanager
    def fake_connect(*_args: object, **_kwargs: object) -> Iterator[object]:
        connects()
        yield object()

    def fake_quotes(
        _conn: object, *, sources: dict[UUID, list[UUID]]
    ) -> dict[UUID, dict[UUID, QuotedPrice]]:
        return {
            response_id: {
                product_id: quotes[(str(response_id), str(product_id))]
                for product_id in product_ids
                if (str(response_id), str(product_id)) in quotes
            }
            for response_id, product_ids in sources.items()
        }

    def fake_quote(
        conn: object, *, rfq_response_id: UUID, product_ids: list[UUID]
    ) -> dict[UUID, QuotedPrice]:
        return fake_quotes(conn, sources={rfq_response_id: product_ids})[rfq_response_id]

    monkeypatch.setattr(service_module.db, "connect", fake_connect)
    monkeypatch.setattr(service_module, "quoted_prices_from_source_response", fake_quote)
    monkeypatch.setattr(
        service_module, "quoted_prices_from_source_responses", fake_quotes, raising=False
    )
    return service, connects, quotes


@pytest.mark.parametrize("sourced", [1, 5, 20])
def test_list_opens_one_connection_for_all_sourced_rows(
    monkeypatch: pytest.MonkeyPatch, sourced: int
) -> None:
    service, connects, _ = _listing(monkeypatch, sourced=sourced, manual=3)
    result = service.list_requests(bearer_token="test", limit=50)
    assert len(result.items) == sourced + 3
    assert connects.call_count == 1


def test_list_with_no_sourced_rows_opens_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    service, connects, _ = _listing(monkeypatch, sourced=0, manual=4)
    service.list_requests(bearer_token="test", limit=50)
    assert connects.call_count == 0


def test_list_keeps_each_rows_own_quoted_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _, quotes = _listing(monkeypatch, sourced=4, manual=2)
    result = service.list_requests(bearer_token="test", limit=50)
    expected = {str(product_id): price.amount for (_, product_id), price in quotes.items()}
    seen = {
        str(line.workspace_product_id): Decimal(line.quoted_unit_price.amount)
        for item in result.items
        for line in item.lines
        if line.quoted_unit_price is not None
    }
    assert seen == expected
