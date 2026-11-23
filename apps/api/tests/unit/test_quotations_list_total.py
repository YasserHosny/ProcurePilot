"""The quotation review queue reports the filtered total for the web pager (PPS-228).

The count rides on the page query itself (PostgREST ``count=exact``), never as a second
round trip.
"""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.quotations import service as service_module
from procurepilot_api.modules.quotations.service import QuotationService, _encode_cursor


def _client(monkeypatch: pytest.MonkeyPatch, *, rows: int, count: int | None) -> Mock:
    data = [
        {
            "id": str(uuid4()),
            "quotation_id": str(uuid4()),
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": "2026-11-01T00:00:00Z",
            "resolved_at": None,
            "quotation": {
                "supplier_id": None,
                "stated_total_amount": "10.00",
                "stated_total_currency": "SAR",
                "supplier": None,
            },
        }
        for _ in range(rows)
    ]
    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.filter.return_value = query
    query.eq.return_value = query
    query.in_.return_value = query
    query.gte.return_value = query
    query.lte.return_value = query
    query.lt.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = lambda: SimpleNamespace(data=data, count=count)
    monkeypatch.setattr(service_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(service_module, "_sync_open_review_tasks", lambda *_: None)
    return client


def test_list_review_tasks_reports_total_from_page_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, rows=3, count=34)
    result = QuotationService().list_review_tasks(bearer_token="test", limit=25)
    assert result.total == 34
    query = client.table.return_value
    assert query.select.call_args.kwargs.get("count") == "exact"
    assert query.execute.call_count == 1


def test_empty_first_page_reports_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _client(monkeypatch, rows=0, count=0)
    assert QuotationService().list_review_tasks(bearer_token="test").total == 0


def test_stale_offset_past_count_is_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "PGRST103", "message": "Requested range not satisfiable", "details": None}
    )
    result = QuotationService().list_review_tasks(
        bearer_token="test", cursor=_encode_cursor(25), limit=25
    )
    assert (result.items, result.next_cursor, result.total) == ([], None, None)


def test_other_database_errors_still_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "57014", "message": "canceling statement due to statement timeout"}
    )
    with pytest.raises(ServiceUnavailableError):
        QuotationService().list_review_tasks(bearer_token="test", limit=25)
