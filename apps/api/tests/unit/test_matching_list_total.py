"""The match resolution queue reports the filtered total for the web pager (PPS-228).

The count rides on the page query itself via ``count(*) over ()``, never as a second
round trip.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching import service as service_module
from procurepilot_api.modules.matching.service import MatchingService, _encode_cursor


def _member() -> CurrentMember:
    return CurrentMember(
        tenant_id=uuid4(),
        user_id=uuid4(),
        membership_id=uuid4(),
        role=MemberRole.buyer,
        email="buyer@example.com",
        bearer_token="test-token",
    )


def _queue_row(total_count: int) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "quotation_id": str(uuid4()),
        "quotation_line_id": str(uuid4()),
        "status": "open",
        "priority": "normal",
        "reason": "low_confidence",
        "created_at": "2026-11-01T00:00:00Z",
        "resolved_at": None,
        "quotation_created_at": "2026-11-01T00:00:00Z",
        "quotation_status": "in_review",
        "quotation_currency": "SAR",
        "quotation_stated_total_amount": "100.00",
        "quotation_stated_total_currency": "SAR",
        "quotation_issue_date": None,
        "quotation_supplier_id": str(uuid4()),
        "supplier_name": "Test Supplier",
        "reviewed_by_email": None,
        "quotation_open_task_count": 1,
        "quotation_total_line_count": 1,
        "line_number": 1,
        "original_text": "Widget",
        "raw_description": "Widget",
        "raw_quantity": "2",
        "raw_unit": "pcs",
        "raw_unit_price": "50.00",
        "raw_line_total": "100.00",
        "top_candidate_product_name": None,
        "top_candidate_confidence": None,
        "top_candidate_rfq_position": None,
        "total_count": total_count,
    }


def _mock_db(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    @contextmanager
    def _auth_db(*_args: object, **_kwargs: object) -> Iterator[MagicMock]:
        yield conn

    monkeypatch.setattr(service_module, "_authenticated_db", _auth_db)
    return cur


def test_match_queue_reports_total_from_single_page_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cur = _mock_db(monkeypatch, [_queue_row(42), _queue_row(42)])
    result = MatchingService().list_match_tasks(
        bearer_token="test", member=_member(), limit=25
    )
    assert result.total == 42
    assert cur.execute.call_count == 1
    sql_text = str(cur.execute.call_args.args[0])
    assert "count(*) over () as total_count" in sql_text


def test_match_queue_empty_first_page_reports_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_db(monkeypatch, [])
    result = MatchingService().list_match_tasks(
        bearer_token="test", member=_member(), limit=25
    )
    assert result.total == 0


def test_match_queue_empty_page_past_first_reports_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_db(monkeypatch, [])
    result = MatchingService().list_match_tasks(
        bearer_token="test", member=_member(), cursor=_encode_cursor(25), limit=25
    )
    assert result.total is None
