from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Money(BaseModel):
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PlanLimits(BaseModel):
    active_catalogue_products: int = Field(ge=0)


class Plan(BaseModel):
    code: str
    name: str
    status: Literal["active", "archived"]
    monthly_price: Money
    limits: PlanLimits
    features: dict[str, Any]


class BillingAccount(BaseModel):
    id: UUID
    plan: Plan
    provider: Literal["stub"]
    provider_customer_id: str
    provider_subscription_id: str | None = None
    status: Literal["active", "past_due", "cancelled"]
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    assigned_at: datetime


class LimitCheck(BaseModel):
    resource: Literal["active_catalogue_products"]
    plan_code: str
    limit: int | None
    used: int = Field(ge=0)
    allowed: bool
    remaining: int | None
