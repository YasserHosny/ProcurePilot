from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from procurepilot_api.modules.requests.budget_status import (
    BudgetRow,
    SpendRow,
    compute_budget_status,
)


def budget(
    *,
    amount: str,
    scope: str = "branch",
    currency: str = "GBP",
    period: str = "monthly",
    period_start: date = date(2026, 9, 1),
    branch_id: UUID | None = None,
    cost_centre_id: UUID | None = None,
) -> BudgetRow:
    return BudgetRow(
        id=uuid4(),
        amount=Decimal(amount),
        currency=currency,
        period=period,
        period_start=period_start,
        scope=scope,
        branch_id=branch_id,
        cost_centre_id=cost_centre_id,
    )


def spend(
    *,
    amount: str,
    request_id: UUID | None = None,
    currency: str = "GBP",
    branch_id: UUID | None = None,
    cost_centre_id: UUID | None = None,
    required_by_date: date = date(2026, 9, 10),
) -> SpendRow:
    return SpendRow(
        request_id=request_id or uuid4(),
        amount=Decimal(amount),
        currency=currency,
        branch_id=branch_id or uuid4(),
        cost_centre_id=cost_centre_id,
        required_by_date=required_by_date,
    )


def test_within_budget_returns_no_status() -> None:
    branch_id = uuid4()
    request_id = uuid4()

    result = compute_budget_status(
        request_id=request_id,
        request_amount=Decimal("40"),
        request_currency="GBP",
        branch_id=branch_id,
        cost_centre_id=None,
        required_by=date(2026, 9, 10),
        budgets=[budget(amount="100", branch_id=branch_id)],
        committed_spend=[
            spend(amount="25", branch_id=branch_id),
            spend(amount="40", request_id=request_id, branch_id=branch_id),
        ],
    )

    assert result is None


def test_exceeding_budget_returns_remaining_amount() -> None:
    branch_id = uuid4()

    result = compute_budget_status(
        request_id=uuid4(),
        request_amount=Decimal("90"),
        request_currency="GBP",
        branch_id=branch_id,
        cost_centre_id=None,
        required_by=date(2026, 9, 10),
        budgets=[budget(amount="100", branch_id=branch_id)],
        committed_spend=[spend(amount="25", branch_id=branch_id)],
    )

    assert result is not None
    assert result.exceeds is True
    assert result.remaining_amount.amount == "75.0000"
    assert result.remaining_amount.currency == "GBP"


def test_no_applicable_budget_returns_no_status() -> None:
    branch_id = uuid4()

    result = compute_budget_status(
        request_id=uuid4(),
        request_amount=Decimal("90"),
        request_currency="GBP",
        branch_id=branch_id,
        cost_centre_id=None,
        required_by=date(2026, 9, 10),
        budgets=[
            budget(
                amount="100",
                currency="USD",
                branch_id=branch_id,
            ),
            budget(
                amount="100",
                branch_id=branch_id,
                period_start=date(2026, 10, 1),
            ),
        ],
        committed_spend=[],
    )

    assert result is None


def test_cost_centre_budget_takes_precedence_over_branch_budget() -> None:
    branch_id = uuid4()
    cost_centre_id = uuid4()

    result = compute_budget_status(
        request_id=uuid4(),
        request_amount=Decimal("80"),
        request_currency="GBP",
        branch_id=branch_id,
        cost_centre_id=cost_centre_id,
        required_by=date(2026, 9, 10),
        budgets=[
            budget(amount="1000", branch_id=branch_id),
            budget(
                amount="100",
                scope="cost_centre",
                branch_id=None,
                cost_centre_id=cost_centre_id,
            ),
        ],
        committed_spend=[
            spend(
                amount="30",
                branch_id=branch_id,
                cost_centre_id=cost_centre_id,
            )
        ],
    )

    assert result is not None
    assert result.exceeds is True
    assert result.remaining_amount.amount == "70.0000"
