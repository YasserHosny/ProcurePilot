from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from dateutil.relativedelta import relativedelta

from procurepilot_api.modules.requests.schemas import BudgetStatus, Money

type BudgetScope = Literal["organisation", "branch", "cost_centre"]
type BudgetPeriod = Literal["monthly", "quarterly", "annual"]


@dataclass(frozen=True)
class BudgetRow:
    id: UUID
    amount: Decimal
    currency: str
    period: BudgetPeriod
    period_start: date
    scope: BudgetScope
    branch_id: UUID | None
    cost_centre_id: UUID | None


@dataclass(frozen=True)
class SpendRow:
    request_id: UUID
    amount: Decimal
    currency: str
    branch_id: UUID
    cost_centre_id: UUID | None
    required_by_date: date


def compute_budget_status(
    *,
    request_id: UUID,
    request_amount: Decimal | None,
    request_currency: str | None,
    branch_id: UUID,
    cost_centre_id: UUID | None,
    required_by: date,
    budgets: list[BudgetRow],
    committed_spend: list[SpendRow],
) -> BudgetStatus | None:
    if request_amount is None or request_currency is None:
        return None

    applicable = [
        budget
        for budget in budgets
        if budget.currency == request_currency
        and _date_in_budget_period(required_by, budget)
        and _budget_targets_request(
            budget,
            branch_id=branch_id,
            cost_centre_id=cost_centre_id,
        )
    ]
    selected = _most_specific_budgets(
        applicable,
        cost_centre_id=cost_centre_id,
    )
    if not selected:
        return None

    period_start = min(budget.period_start for budget in selected)
    period_end = max(_budget_period_end(budget) for budget in selected)
    budget_amount = sum((budget.amount for budget in selected), Decimal("0"))
    spent_amount = sum(
        (
            spend.amount
            for spend in committed_spend
            if spend.request_id != request_id
            and spend.currency == request_currency
            and period_start <= spend.required_by_date < period_end
            and _spend_matches_budget_scope(
                spend,
                scope=selected[0].scope,
                branch_id=branch_id,
                cost_centre_id=cost_centre_id,
            )
        ),
        Decimal("0"),
    )
    remaining = budget_amount - spent_amount
    if request_amount <= remaining:
        return None
    return BudgetStatus(
        remaining_amount=Money(
            amount=_format_decimal(remaining),
            currency=request_currency,
        ),
        exceeds=True,
    )


def _most_specific_budgets(
    budgets: list[BudgetRow],
    *,
    cost_centre_id: UUID | None,
) -> list[BudgetRow]:
    if cost_centre_id is not None:
        cost_centre_budgets = [
            budget for budget in budgets if budget.scope == "cost_centre"
        ]
        if cost_centre_budgets:
            return cost_centre_budgets
    branch_budgets = [budget for budget in budgets if budget.scope == "branch"]
    if branch_budgets:
        return branch_budgets
    return [budget for budget in budgets if budget.scope == "organisation"]


def _budget_targets_request(
    budget: BudgetRow,
    *,
    branch_id: UUID,
    cost_centre_id: UUID | None,
) -> bool:
    if budget.scope == "organisation":
        return True
    if budget.scope == "branch":
        return budget.branch_id == branch_id
    return (
        cost_centre_id is not None
        and budget.cost_centre_id == cost_centre_id
    )


def _spend_matches_budget_scope(
    spend: SpendRow,
    *,
    scope: BudgetScope,
    branch_id: UUID,
    cost_centre_id: UUID | None,
) -> bool:
    if scope == "organisation":
        return True
    if scope == "branch":
        return spend.branch_id == branch_id
    return (
        cost_centre_id is not None
        and spend.cost_centre_id == cost_centre_id
    )


def _date_in_budget_period(value: date, budget: BudgetRow) -> bool:
    return budget.period_start <= value < _budget_period_end(budget)


def _budget_period_end(budget: BudgetRow) -> date:
    months = {"monthly": 1, "quarterly": 3, "annual": 12}[budget.period]
    return budget.period_start + relativedelta(months=months)


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")
