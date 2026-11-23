"""The Purchasing history totals come back with the rows of the page."""

from contextlib import nullcontext
from datetime import UTC, date, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers import basket_service
from procurepilot_api.modules.rfq import service as rfq_service


@pytest.fixture
def member() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


@pytest.mark.parametrize(
    ("offset", "has_rows", "expected"), [(25, True, 34), (0, False, 0), (25, False, None)]
)
def test_rfq_total_is_counted_before_limit_and_offset(
    monkeypatch: pytest.MonkeyPatch,
    member: CurrentMember,
    offset: int,
    has_rows: bool,
    expected: int | None,
) -> None:
    row = {
        "id": uuid4(),
        "reference_number": 1,
        "status": "draft",
        "needed_by_date": date(2026, 11, 30),
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
        "created_by_membership_id": member.membership_id,
        "recipient_count": 1,
        "response_count": 0,
        "total": 34,
    }
    cur = Mock()
    cur.fetchall.return_value = [row] if has_rows else []
    conn = Mock()
    conn.cursor.return_value = nullcontext(cur)
    monkeypatch.setattr(rfq_service, "_authenticated_db", lambda *_: nullcontext(conn))

    page = rfq_service.RfqService(get_settings()).list_rfqs(
        member=member,
        status="draft",
        cursor=rfq_service._encode_cursor(offset) if offset else None,
        limit=25,
    )

    assert page.total == expected
    cur.execute.assert_called_once()
    query, params = cur.execute.call_args.args
    assert "count(*) over () as total" in query
    assert "WHERE r.tenant_id = %s" in query and "LIMIT %s OFFSET %s" in query
    assert params == (member.tenant_id, "draft", 26, offset)


@pytest.mark.parametrize(
    ("has_cursor", "has_rows", "expected"),
    [(True, True, 34), (False, False, 0), (True, False, None)],
)
def test_basket_total_is_in_the_page_query_and_ignores_the_cursor(
    monkeypatch: pytest.MonkeyPatch,
    member: CurrentMember,
    has_cursor: bool,
    has_rows: bool,
    expected: int | None,
) -> None:
    row = {
        "id": uuid4(),
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
        "status": "completed",
        "supplier_ids": [uuid4(), uuid4()],
        "item_count": 1,
        "total": 34,
    }
    cur = Mock()
    cur.fetchall.side_effect = [[row] if has_rows else [], []]
    conn = Mock()
    conn.cursor.return_value = nullcontext(cur)
    monkeypatch.setattr(basket_service, "_authenticated_db", lambda *_: nullcontext(conn))
    cursor = basket_service._encode_history_cursor(row) if has_cursor else None

    page = basket_service.BasketService().list_jobs(member=member, cursor=cursor, limit=25)

    assert page.total == expected
    assert cur.execute.call_count == 2  # The counted page and the existing supplier name lookup.
    query, params = cur.execute.call_args_list[0].args
    assert "(select count(*) from basket_split_job) as total" in query
    assert ("(created_at, id) <" in query) == has_cursor
    position = [row["created_at"].isoformat(), str(row["id"])] if has_cursor else []
    assert params == [*position, 26]
