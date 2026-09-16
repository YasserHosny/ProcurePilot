from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DigestChannel = Literal["in_app", "email"]
DigestStatus = Literal["active", "paused"]
DeliveryStatus = Literal["succeeded", "failed", "email_unconfigured"]
DigestSectionKind = Literal[
    "verified_savings",
    "pending_verifications",
    "pending_approvals",
    "anomalies",
    "expiring_validity",
]


class DigestFilters(BaseModel):
    branch_id: UUID | None = None


class DigestSubscriptionCreate(BaseModel):
    filters: DigestFilters = Field(default_factory=DigestFilters)
    locale: Literal["en", "ar"] | None = None
    channel: DigestChannel = "in_app"


class DigestSubscriptionUpdate(BaseModel):
    filters: DigestFilters | None = None
    locale: Literal["en", "ar"] | None = None
    channel: DigestChannel | None = None
    status: DigestStatus | None = None


class DigestSubscription(BaseModel):
    id: UUID
    kind: Literal["weekly_digest"] = "weekly_digest"
    filters: DigestFilters
    channel: DigestChannel
    status: DigestStatus
    locale: Literal["en", "ar"]
    next_run_at: datetime
    last_delivery_at: datetime | None = None
    last_delivery_status: DeliveryStatus | None = None
    email_configured: bool = False
    created_at: datetime
    updated_at: datetime


class DigestSubscriptionList(BaseModel):
    items: list[DigestSubscription]
    next_cursor: str | None = None


class DigestMoney(BaseModel):
    amount: float
    currency: str = Field(pattern="^[A-Z]{3}$")


class DigestItem(BaseModel):
    label: str
    money: DigestMoney | None = None
    evidence_ref: str | None = None
    deep_link: str


class DigestSection(BaseModel):
    kind: DigestSectionKind
    items: list[DigestItem]


class DigestView(BaseModel):
    subscription_id: UUID
    period_start: date
    period_end: date
    sections: list[DigestSection]
    rendered_at: datetime
    delivery_status: DeliveryStatus
