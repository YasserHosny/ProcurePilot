"""List enrichment must reuse reads without changing single-request output."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.requests import service as service_module
from procurepilot_api.modules.requests.budget_status import BudgetRow, SpendRow
from procurepilot_api.modules.requests.service import RequestsService

type Listing = tuple[RequestsService, Mock, Mock]


@pytest.fixture
def listing(monkeypatch: pytest.MonkeyPatch) -> Listing:
    service = RequestsService()
    branch, member = uuid4(), uuid4()
    rows = [
        {
            "id": str(uuid4()),
            "branch_id": str(branch),
            "requested_by_membership_id": str(member),
            "required_by_date": "2026-11-12",
            "status": "approved",
            "estimated_total_amount": str(10 + i * 10),
            "estimated_total_currency": "GBP" if i % 2 else "USD",
            "created_at": "2026-11-01T00:00:00Z",
        }
        for i in range(8)
    ]
    rows[-2]["estimated_total_amount"] = None
    rows[-1]["estimated_total_currency"] = "EUR"
    budgets = [
        BudgetRow(
            uuid4(),
            Decimal("150"),
            currency,
            "monthly",
            date(2026, 11, 1),
            "organisation",
            None,
            None,
        )
        for currency in ("USD", "GBP")
    ]
    spend = [
        SpendRow(
            UUID(row["id"]),
            Decimal(row["estimated_total_amount"]),
            row["estimated_total_currency"],
            branch,
            None,
            date(2026, 11, 12),
        )
        for row in rows[:6]
    ]
    client = Mock()
    query = client.table.return_value
    query.select.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.side_effect = lambda: SimpleNamespace(data=rows)
    monkeypatch.setattr(service_module, "authenticated_client", lambda *_: client)
    for name in (
        "_fetch_lines_batch",
        "_fetch_steps_batch",
        "_fetch_member_contacts_batch",
        "_fetch_auto_prepared_batch",
        "_fetch_sources_batch",
        "_fetch_request_groups_batch",
    ):
        monkeypatch.setattr(service, name, Mock(return_value={}))
    monkeypatch.setattr(
        service, "_fetch_request", lambda _, rid: next(row for row in rows if row["id"] == str(rid))
    )
    monkeypatch.setattr(service, "_fetch_lines_for", Mock(return_value=[]))
    monkeypatch.setattr(service, "_fetch_step", Mock(return_value=None))
    budget_fetch = Mock(return_value=budgets)
    spend_fetch = Mock(
        side_effect=lambda _, budget: [row for row in spend if row.currency == budget.currency]
    )
    monkeypatch.setattr(service, "_fetch_budget_rows", budget_fetch)
    monkeypatch.setattr(service, "_fetch_committed_spend_rows", spend_fetch)
    return service, budget_fetch, spend_fetch


def test_list_budget_fetch_count_is_constant(listing: Listing) -> None:
    service, budget_fetch, spend_fetch = listing
    for size in (5, 8):
        result = service.list_requests(bearer_token="test", limit=size)
        assert len(result.items) == size
        assert (budget_fetch.call_count, spend_fetch.call_count) == (1, 2)
        assert len({call.args[1].id for call in spend_fetch.call_args_list}) == 2
        budget_fetch.reset_mock()
        spend_fetch.reset_mock()


def test_list_budget_status_matches_single_request(listing: Listing) -> None:
    service, budget_fetch, spend_fetch = listing
    for iteration in range(2):
        result = service.list_requests(bearer_token="test")
        for item in result.items:
            single = service.get_request(bearer_token="test", request_id=item.id)
            assert item.budget_status == single.budget_status
            assert item.model_dump_json() == single.model_dump_json()
        assert {item.budget_status.status for item in result.items if item.budget_status} == (
            {"within", "near", "no_budget"} if iteration == 0 else {"within", "no_budget"}
        )
        assert result.items[-2].budget_status is None
        # A later call must observe changed spend rather than reuse the prior list's cache.
        spend_fetch.side_effect = lambda *_: []
