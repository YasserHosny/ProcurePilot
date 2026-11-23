"""The member list reports the filtered total for the web pager (PPS-228).

The count rides on the page query itself (PostgREST ``count=exact``), never as a second
round trip.
"""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.members import service as service_module
from procurepilot_api.modules.members.service import MemberService, _encode_cursor


def _service(monkeypatch: pytest.MonkeyPatch, *, rows: int, count: int | None) -> Mock:
    data = [
        {
            "id": str(uuid4()),
            "email": f"user{i}@example.com",
            "display_name": f"User {i}",
            "role": "buyer",
            "status": "active",
            "mfa_enabled": False,
            "created_at": "2026-11-01T00:00:00Z",
        }
        for i in range(rows)
    ]
    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = lambda: SimpleNamespace(data=data, count=count)
    monkeypatch.setattr(service_module, "authenticated_client", lambda *_: client)
    return client


def test_list_members_reports_total_from_the_page_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _service(monkeypatch, rows=3, count=34)
    result = MemberService().list_members(bearer_token="test", limit=25)
    assert result.total == 34
    query = client.table.return_value
    assert query.select.call_args.kwargs.get("count") == CountMethod.exact
    assert query.execute.call_count == 1


def test_empty_first_page_reports_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _service(monkeypatch, rows=0, count=0)
    assert MemberService().list_members(bearer_token="test").total == 0


def test_stale_offset_past_the_count_is_an_empty_page_not_an_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _service(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "PGRST103", "message": "Requested range not satisfiable", "details": None}
    )
    result = MemberService().list_members(bearer_token="test", cursor=_encode_cursor(25), limit=25)
    assert (result.items, result.next_cursor, result.total) == ([], None, None)


def test_other_database_errors_still_report_the_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _service(monkeypatch, rows=0, count=None)
    client.table.return_value.execute.side_effect = APIError(
        {"code": "57014", "message": "canceling statement due to statement timeout"}
    )
    with pytest.raises(ServiceUnavailableError):
        MemberService().list_members(bearer_token="test", limit=25)
