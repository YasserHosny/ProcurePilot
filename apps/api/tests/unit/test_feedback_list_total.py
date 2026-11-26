"""Feedback list endpoints report the filtered total in the page query (PPS-228).

Keyset cursors must count all matching rows via a scalar subquery that excludes the cursor
predicate, in the same single SQL execute on the same RLS-scoped connection.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.operator import CurrentOperator
from procurepilot_api.modules.feedback import operator_service as op_service_module
from procurepilot_api.modules.feedback import service as fb_service_module
from procurepilot_api.modules.feedback.operator_service import OperatorFeedbackService
from procurepilot_api.modules.feedback.operator_service import (
    encode_cursor as encode_op_cursor,
)
from procurepilot_api.modules.feedback.schemas import Category, Status
from procurepilot_api.modules.feedback.service import FeedbackService
from procurepilot_api.modules.feedback.service import (
    encode_cursor as encode_fb_cursor,
)


def _member(role: MemberRole = MemberRole.owner) -> CurrentMember:
    return CurrentMember(
        user_id=uuid4(),
        tenant_id=uuid4(),
        membership_id=uuid4(),
        role=role,
        email="owner@example.test",
    )


def _operator() -> CurrentOperator:
    return CurrentOperator(
        user_id=uuid4(),
        tenant_id=uuid4(),
        membership_id=uuid4(),
        role=MemberRole.owner,
        email="op@example.test",
    )


def _submission_row(*, total_count: int, member: CurrentMember) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": member.tenant_id,
        "submitter_user_id": member.user_id,
        "submitter_name": "Owner",
        "member_role": member.role.value,
        "text_content": "Feedback text",
        "category": "bug",
        "status": "new",
        "page_path": "/home",
        "locale": "en",
        "created_at": datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        "total_count": total_count,
    }


def _op_row(*, total_count: int) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "text_content": "Operator feedback",
        "category": "bug",
        "status": "new",
        "submitter_name": "Buyer",
        "submitter_email": "buyer@example.test",
        "member_role": "buyer",
        "page_path": "/home",
        "locale": "en",
        "created_at": datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        "labels": [],
        "app_version": "1",
        "is_demo": False,
        "status_changed_at": None,
        "total_count": total_count,
    }


def _mock_conn(rows: list[dict[str, object]]) -> tuple[MagicMock, MagicMock]:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_feedback_list_mine_and_workspace_count_in_one_execute_ignoring_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = _member()
    rows = [_submission_row(total_count=42, member=member)]
    conn, cur = _mock_conn(rows)

    @contextmanager
    def fake_db(*_: object, **__: object) -> Iterator[MagicMock]:
        yield conn

    monkeypatch.setattr(fb_service_module, "_feedback_db", fake_db)
    monkeypatch.setattr(fb_service_module, "_fetch_attachments", lambda *_: {})
    svc = FeedbackService(storage=Mock())

    cursor = encode_fb_cursor(datetime(2026, 11, 18, 12, 0, tzinfo=UTC), uuid4())
    page = svc.list_workspace(
        member=member, cursor=cursor, limit=25, status=Status.new, category=Category.bug
    )

    assert page.total == 42
    assert cur.execute.call_count == 1
    sql, params = cur.execute.call_args.args
    subquery, _, outer = sql.partition("from feedback_submission where ")
    assert "(created_at, id) < (%s, %s)" not in subquery
    assert "(created_at, id) < (%s, %s)" in outer
    assert params[-1] == 26  # limit + 1


def test_feedback_empty_pages_report_zero_on_first_and_none_past_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = _member(MemberRole.buyer)
    conn, _ = _mock_conn([])

    @contextmanager
    def fake_db(*_: object, **__: object) -> Iterator[MagicMock]:
        yield conn

    monkeypatch.setattr(fb_service_module, "_feedback_db", fake_db)
    monkeypatch.setattr(fb_service_module, "_fetch_attachments", lambda *_: {})
    svc = FeedbackService(storage=Mock())

    assert svc.list_mine(member=member).total == 0
    cursor = encode_fb_cursor(datetime(2026, 11, 18, 12, 0, tzinfo=UTC), uuid4())
    assert svc.list_mine(member=member, cursor=cursor).total is None


def test_operator_feedback_counts_in_one_execute_ignoring_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator()
    rows = [_op_row(total_count=17)]
    conn, cur = _mock_conn(rows)

    @contextmanager
    def fake_op_conn(*_: object, **__: object) -> Iterator[MagicMock]:
        yield conn

    monkeypatch.setattr(op_service_module, "operator_connection", fake_op_conn)
    monkeypatch.setattr(OperatorFeedbackService, "_hydrate", staticmethod(lambda *_: []))
    svc = OperatorFeedbackService(audit_writer=Mock(), signer=Mock())

    cursor = encode_op_cursor(datetime(2026, 11, 18, 12, 0, tzinfo=UTC), uuid4())
    page = svc.list_feedback(operator, is_demo=False, cursor=cursor, limit=10)

    assert page.total == 17
    assert cur.execute.call_count == 1
    sql, params = cur.execute.call_args.args
    subquery, _, outer = sql.partition("from feedback_submission s where ")
    assert "(s.created_at, s.id) < (%s, %s)" not in subquery
    assert "(s.created_at, s.id) < (%s, %s)" in outer
    assert params[-1] == 11  # limit + 1


def test_operator_empty_pages_report_zero_on_first_and_none_past_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = _operator()
    conn, _ = _mock_conn([])

    @contextmanager
    def fake_op_conn(*_: object, **__: object) -> Iterator[MagicMock]:
        yield conn

    monkeypatch.setattr(op_service_module, "operator_connection", fake_op_conn)
    monkeypatch.setattr(OperatorFeedbackService, "_hydrate", staticmethod(lambda *_: []))
    svc = OperatorFeedbackService(audit_writer=Mock(), signer=Mock())

    assert svc.list_feedback(operator).total == 0
    cursor = encode_op_cursor(datetime(2026, 11, 18, 12, 0, tzinfo=UTC), uuid4())
    assert svc.list_feedback(operator, cursor=cursor).total is None
