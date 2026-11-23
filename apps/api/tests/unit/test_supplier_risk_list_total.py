"""The supplier risk queue reports the total for the web pager (PPS-228).

Keyset pagination uses a scalar subquery in the same SQL statement without the cursor
predicate, never ``count(*) over ()`` (which would only count rows after the cursor).
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from procurepilot_api.modules.offers.supplier_iq_repository import (
    _encode_cursor,
    list_latest,
)


def _snapshot_row(total_count: int) -> dict[str, object]:
    return {
        "id": uuid4(),
        "supplier_id": uuid4(),
        "supplier_name": "Alfaisal Trade",
        "window_start": date(2026, 3, 24),
        "window_end": date(2026, 9, 20),
        "state": "ready",
        "confidence": "high",
        "release_posture": "g3_unmet",
        "valid_from": datetime(2026, 9, 20, tzinfo=UTC),
        "valid_until": datetime(2099, 9, 21, tzinfo=UTC),
        "source_fingerprint": "fp-1",
        "observed_history_days": 180,
        "risk_score": {"total": "0.7200", "components": {}, "weights": {}},
        "risk_level": "high",
        "computed_at": datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        "total_count": total_count,
    }


def _mock_conn(rows: list[dict[str, object]]) -> tuple[MagicMock, MagicMock]:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_list_latest_reports_total_from_single_query_ignoring_keyset_cursor() -> None:
    row = _snapshot_row(19)
    cursor = _encode_cursor(row)
    conn, cur = _mock_conn([_snapshot_row(19)])

    page = list_latest(conn, cursor=cursor, limit=25)

    assert page.total == 19
    assert cur.execute.call_count == 1
    sql_text = str(cur.execute.call_args.args[0])
    assert "(select count(*) from ranked where row_number = 1) as total_count" in sql_text
    assert "count(*) over ()" not in sql_text
    assert "total_count" not in page.items[0]


def test_list_latest_empty_first_page_reports_zero() -> None:
    conn, _ = _mock_conn([])
    page = list_latest(conn, cursor=None, limit=25)
    assert page.total == 0


def test_list_latest_empty_page_past_first_reports_none() -> None:
    conn, _ = _mock_conn([])
    cursor = _encode_cursor(_snapshot_row(0))
    page = list_latest(conn, cursor=cursor, limit=25)
    assert page.total is None
