from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.organisation.schemas import (
    Budget,
    BudgetCreate,
    BudgetCreated,
    BudgetList,
    Money,
)


def test_budget_contract_accepts_each_scope() -> None:
    organisation_wide = Budget(
        id=uuid4(),
        amount=Money(amount="5000.0000", currency="GBP"),
        period="annual",
        period_start="2026-01-01",
        scope="organisation",
        created_at="2026-08-22T00:00:00Z",
    )
    assert organisation_wide.branch_id is None
    assert organisation_wide.cost_centre_id is None

    branch_scoped = organisation_wide.model_copy(
        update={"scope": "branch", "branch_id": uuid4(), "period": "monthly"}
    )
    assert branch_scoped.branch_id is not None

    cost_centre_scoped = organisation_wide.model_copy(
        update={"scope": "cost_centre", "cost_centre_id": uuid4(), "period": "quarterly"}
    )
    assert cost_centre_scoped.cost_centre_id is not None

    assert BudgetList(items=[organisation_wide], next_cursor=None).items[0].scope == "organisation"


def test_budget_created_adds_overlap_warning_on_top_of_budget() -> None:
    created = BudgetCreated(
        id=uuid4(),
        amount=Money(amount="1000.0000", currency="GBP"),
        period="monthly",
        period_start="2026-08-01",
        scope="organisation",
        created_at="2026-08-22T00:00:00Z",
        overlap_warning=True,
    )
    assert created.overlap_warning is True

    default_false = BudgetCreated(
        id=uuid4(),
        amount=Money(amount="1000.0000", currency="GBP"),
        period="monthly",
        period_start="2026-08-01",
        scope="organisation",
        created_at="2026-08-22T00:00:00Z",
    )
    assert default_false.overlap_warning is False


def test_budget_create_uses_flat_amount_and_currency_not_nested_money() -> None:
    """Deliberate contract asymmetry: Budget.amount is nested Money on read, but BudgetCreate
    takes flat amount+currency strings on write — this is intentional, not a bug to fix."""
    payload = BudgetCreate(
        amount="2500.0000",
        currency="GBP",
        period="annual",
        period_start="2026-01-01",
        scope="organisation",
    )
    assert payload.amount == "2500.0000"
    assert payload.currency == "GBP"


def test_budget_create_amount_rejects_a_negative_value() -> None:
    """Unlike Money's own pattern (which allows a leading '-' for cases like a discount), a
    budget amount itself is never negative — the contract's BudgetCreate schema uses a
    non-negative-only pattern."""
    with pytest.raises(ValidationError):
        BudgetCreate(
            amount="-100.0000",
            currency="GBP",
            period="monthly",
            period_start="2026-08-01",
            scope="organisation",
        )


def test_budget_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        BudgetCreate.model_validate(
            {
                "amount": "100.0000",
                "currency": "GBP",
                "period": "monthly",
                "period_start": "2026-08-01",
                "scope": "organisation",
                "overlap_warning": True,
            }
        )


def test_budget_create_rejects_an_unknown_scope_or_period() -> None:
    with pytest.raises(ValidationError):
        BudgetCreate(
            amount="100.0000",
            currency="GBP",
            period="weekly",  # type: ignore[arg-type]
            period_start="2026-08-01",
            scope="organisation",
        )
    with pytest.raises(ValidationError):
        BudgetCreate(
            amount="100.0000",
            currency="GBP",
            period="monthly",
            period_start="2026-08-01",
            scope="department",  # type: ignore[arg-type]
        )
