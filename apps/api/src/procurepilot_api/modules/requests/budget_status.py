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
    chosen = _current_period_budget(selected)
    if chosen is None:
        return None

    period_start = chosen.period_start
    period_end = _budget_period_end(chosen)
    budget_amount = chosen.amount
    spent_amount = sum(
        (
            spend.amount
            for spend in committed_spend
            if spend.request_id != request_id
            and spend.currency == request_currency
            and period_start <= spend.required_by_date < period_end
            and _spend_matches_budget_scope(
                spend,
                scope=chosen.scope,
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


_PERIOD_RANK: dict[BudgetPeriod, int] = {
    "monthly": 0,
    "quarterly": 1,
    "annual": 2,
}


def _current_period_budget(budgets: list[BudgetRow]) -> BudgetRow | None:
    """FR-011 compares a request against *one* budget — "whichever R2.0 budget applies to its
    scope for the current period". ``_most_specific_budgets`` has already narrowed to a single
    scope tier; when several budgets at that tier still overlap the request's required-by date
    (the data model deliberately allows it — e.g. a running annual budget plus a supplementary
    quarterly top-up, see the ``budget`` migration), pick the one that most tightly bounds
    "now": shortest period, then latest start, then id for a deterministic result.

    This mirrors the narrowest-range-wins tie-break routing already uses (research.md R3). It
    deliberately does NOT sum amounts or union the periods of overlapping budgets — that would
    double-count spend that draws down both and invent an envelope no owner defined; a genuine
    overlap is surfaced as a warning at budget-creation time (R2.0), not reconciled here.
    """
    if not budgets:
        return None
    return min(
        budgets,
        key=lambda budget: (
            _PERIOD_RANK[budget.period],
            -budget.period_start.toordinal(),
            str(budget.id),
        ),
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
