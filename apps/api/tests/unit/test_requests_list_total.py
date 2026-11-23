"""The request list reports the filtered total for the web pager (PPS-228).

The count rides on the page query itself (PostgREST ``count=exact``), never as a second
round trip.
"""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.requests import service as service_module
from procurepilot_api.modules.requests.service import RequestsService, _encode_cursor


def _service(monkeypatch: pytest.MonkeyPatch, *, rows: int, count: int | None) -> Mock:
    branch, member = str(uuid4()), str(uuid4())
    data = [
        {
            "id": str(uuid4()),
            "branch_id": branch,
            "requested_by_membership_id": member,
            "required_by_date": "2026-11-30",
            "status": "draft",
            "estimated_total_amount": "10",
            "estimated_total_currency": "SAR",
            "created_at": "2026-11-01T00:00:00Z",
        }
        for _ in range(rows)
    ]
    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = lambda: SimpleNamespace(data=data, count=count)
    monkeypatch.setattr(service_module, "authenticated_client", lambda *_: client)
    return client


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> RequestsService:
    svc = RequestsService()
    for name in (
        "_fetch_lines_batch",
        "_fetch_steps_batch",
        "_fetch_member_contacts_batch",
        "_fetch_auto_prepared_batch",
        "_fetch_sources_batch",
        "_fetch_request_groups_batch",
    ):
        monkeypatch.setattr(svc, name, Mock(return_value={}))
    monkeypatch.setattr(svc, "_fetch_budget_rows", Mock(return_value=[]))
    return svc


def test_list_reports_total_from_the_page_query(
    monkeypatch: pytest.MonkeyPatch, service: RequestsService
) -> None:
    client = _service(monkeypatch, rows=3, count=34)
    result = service.list_requests(bearer_token="test", limit=25)
    assert result.total == 34
    query = client.table.return_value
    assert query.select.call_args.kwargs.get("count") == "exact"
    assert query.execute.call_count == 1


def test_empty_first_page_reports_zero(
    monkeypatch: pytest.MonkeyPatch, service: RequestsService
) -> None:
    _service(monkeypatch, rows=0, count=0)
    assert service.list_requests(bearer_token="test").total == 0


def test_stale_offset_past_the_count_is_an_empty_page_not_an_outage(
    monkeypatch: pytest.MonkeyPatch, service: RequestsService
) -> None:
    # With count=exact, PostgREST answers an offset past the current total with 416/PGRST103,
    # e.g. a list that shrank between pages. That is an empty page, not a database outage.
    client = _service(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "PGRST103", "message": "Requested range not satisfiable", "details": None}
    )
    result = service.list_requests(bearer_token="test", cursor=_encode_cursor(25), limit=25)
    assert (result.items, result.next_cursor, result.total) == ([], None, None)


def test_other_database_errors_still_report_the_outage(
    monkeypatch: pytest.MonkeyPatch, service: RequestsService
) -> None:
    client = _service(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "57014", "message": "canceling statement due to statement timeout"}
    )
    with pytest.raises(ServiceUnavailableError):
        service.list_requests(bearer_token="test", limit=25)
