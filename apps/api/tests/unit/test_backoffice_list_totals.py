"""Back-office totals ride on the authenticated page query (PPS-228)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from procurepilot_api.modules.accounting import reconciliation_service
from procurepilot_api.modules.accounting import service as accounting_service
from procurepilot_api.modules.analyst import service as analyst_service
from procurepilot_api.modules.analyst.schemas import AnalystConversationResponse
from procurepilot_api.modules.ingestion import email_log_service
from procurepilot_api.modules.reports import schedules

NOW = datetime(2026, 9, 17, tzinfo=UTC)
ROW_ID = uuid4()
MEMBER = SimpleNamespace(
    tenant_id=uuid4(), membership_id=uuid4(), role=SimpleNamespace(value="owner")
)
REPORT_ROW = {
    "kind": "savings_ledger",
    "format": "csv",
    "locale": "en",
    "filters": {},
    "created_at": NOW,
}


def _mock_page_query(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, rows: list[dict[str, object]]
) -> MagicMock:
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def authenticated_db(_settings: object, member: object) -> Iterator[MagicMock]:
        assert member is MEMBER
        yield conn

    monkeypatch.setattr(module, "_authenticated_db", authenticated_db)
    return cursor


@pytest.mark.parametrize(
    ("module", "service_class", "method", "filters", "predicates", "row"),
    [
        pytest.param(
            accounting_service,
            accounting_service.ConnectionService,
            "list_bills",
            {"match_status": "unmatched"},
            ("b.tenant_id = %(tenant_id)s", "m.id is null"),
            {
                "vendor_name": "Supplier",
                "amount": "20.00",
                "currency": "EUR",
                "bill_date": NOW.date(),
                "provider_status": "open",
                "matched": False,
            },
            id="bills",
        ),
        pytest.param(
            reconciliation_service,
            reconciliation_service.ReconciliationService,
            "list_discrepancies",
            {"status": "open"},
            ("d.tenant_id = %(tenant_id)s", "d.status = %(status)s"),
            {"discrepancy_type": "unmatched_bill", "status": "open", "detected_at": NOW},
            id="discrepancies",
        ),
        pytest.param(
            email_log_service,
            email_log_service.IngestionEmailLogService,
            "list_email_logs",
            {"status": "completed", "from_domain": "example.test", "date_from": "2026-09-01"},
            ("l.status = %(status)s", "l.from_domain = %(from_domain)s", "l.received_at >="),
            {
                "message_id": "test-message",
                "from_address": "sender@example.test",
                "from_domain": "example.test",
                "received_at": NOW,
                "created_at": NOW,
                "status": "completed",
                "attachment_count": 1,
            },
            id="email-log",
        ),
        pytest.param(
            schedules,
            schedules.ReportsService,
            "list_artifacts",
            {"kind": "savings_ledger", "status": "completed"},
            ("kind = %(kind)s", "status = %(status)s"),
            {**REPORT_ROW, "status": "completed"},
            id="report-artifacts",
        ),
        pytest.param(
            schedules,
            schedules.ReportsService,
            "list_schedules",
            {},
            (),
            {
                **REPORT_ROW,
                "status": "active",
                "weekday": 0,
                "next_run_at": NOW,
                "updated_at": NOW,
            },
            id="report-schedules",
        ),
    ],
)
def test_offset_total_comes_from_one_page_query(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    service_class: type,
    method: str,
    filters: dict[str, str],
    predicates: tuple[str, ...],
    row: dict[str, object],
) -> None:
    cursor = _mock_page_query(monkeypatch, module, [{**row, "id": ROW_ID, "total_count": 26}])
    list_page = getattr(service_class(settings=SimpleNamespace()), method)

    page = list_page(member=MEMBER, cursor="MjU=", limit=25, **filters)

    assert [item.id for item in page.items] == [ROW_ID]
    assert page.total == 26
    assert page.next_cursor is None
    assert cursor.execute.call_count == 1
    query, params = cursor.execute.call_args.args
    assert "count(*) over () as total_count" in query
    assert all(predicate in query for predicate in predicates)
    assert params["limit"] == 26
    assert params["offset"] == 25

    cursor.fetchall.return_value = []
    assert list_page(member=MEMBER, **filters).total == 0
    assert list_page(member=MEMBER, cursor="MjU=", **filters).total is None


def test_history_total_ignores_the_cursor_in_the_page_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _mock_page_query(
        monkeypatch, analyst_service, [{"id": ROW_ID, "created_at": NOW, "total_count": 26}]
    )
    conversation = AnalystConversationResponse(
        id=ROW_ID,
        tenant_id=MEMBER.tenant_id,
        creating_member_id=MEMBER.membership_id,
        created_at=NOW,
    )
    # History still hydrates each conversation through the existing detail reader.
    monkeypatch.setattr(
        analyst_service, "_build_conversation_response", Mock(return_value=conversation)
    )
    service = analyst_service.AnalystService(settings=SimpleNamespace(), intent_provider=Mock())
    after_id = uuid4()
    after = analyst_service._encode_conversation_cursor(NOW, after_id)

    page = service.list_conversations(member=MEMBER, cursor=after, limit=25)

    assert page.items == [conversation]
    assert page.total == 26
    assert page.next_cursor is None
    assert cursor.execute.call_count == 1
    query, params = cursor.execute.call_args.args
    assert "(select count(*) from analyst_conversation) as total_count" in query
    assert "where (created_at, id) < (%s, %s)" in query
    assert params == (NOW, after_id, 26)

    cursor.fetchall.return_value = []
    assert service.list_conversations(member=MEMBER).total == 0
    assert service.list_conversations(member=MEMBER, cursor=after).total is None
