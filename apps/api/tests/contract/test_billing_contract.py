from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from procurepilot_api.modules.billing.schemas import (
    BillingAccount,
    LimitCheck,
    Money,
    Plan,
    PlanLimits,
)


def test_billing_account_contract_has_plan_money_and_stub_provider() -> None:
    account = BillingAccount(
        id=uuid4(),
        plan=Plan(
            code="starter",
            name="Starter",
            status="active",
            monthly_price=Money(amount=Decimal("0.0000"), currency="GBP"),
            limits=PlanLimits(active_catalogue_products=100),
            features={},
        ),
        provider="stub",
        provider_customer_id="stub_customer:tenant",
        provider_subscription_id="stub_subscription:tenant:starter",
        status="active",
        assigned_at=datetime.now(UTC),
    )

    body = account.model_dump(mode="json")
    assert body["provider"] == "stub"
    assert body["plan"]["monthly_price"] == {"amount": "0.0000", "currency": "GBP"}
    assert body["plan"]["limits"]["active_catalogue_products"] == 100


def test_limit_check_contract_reports_remaining_capacity() -> None:
    check = LimitCheck(
        resource="active_catalogue_products",
        plan_code="starter",
        limit=100,
        used=99,
        allowed=True,
        remaining=1,
    )

    assert check.model_dump(mode="json")["remaining"] == 1
