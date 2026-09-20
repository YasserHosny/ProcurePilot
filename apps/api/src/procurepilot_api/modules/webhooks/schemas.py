from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field

type WebhookSubscriptionStatus = Literal["active", "paused", "revoked"]
type WebhookDeliveryStatus = Literal["pending", "processing", "succeeded", "failed"]


class WebhookSubscriptionCreate(BaseModel):
    endpoint_url: AnyHttpUrl
    events: list[str] = Field(default_factory=lambda: ["*"] , min_length=1, max_length=50)


class WebhookSubscription(BaseModel):
    id: UUID
    endpoint_url: AnyHttpUrl
    events: list[str]
    status: WebhookSubscriptionStatus
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreated(WebhookSubscription):
    secret: str


class WebhookSubscriptionList(BaseModel):
    items: list[WebhookSubscription]


class WebhookDelivery(BaseModel):
    id: UUID
    subscription_id: UUID
    event_id: int
    event_type: str
    status: WebhookDeliveryStatus
    attempts: int
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    last_error: str | None
    created_at: datetime


class WebhookDeliveryList(BaseModel):
    items: list[WebhookDelivery]
