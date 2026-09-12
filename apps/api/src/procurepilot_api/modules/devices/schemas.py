from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

type DevicePlatform = Literal["ios", "android"]
type PushNotificationStatus = Literal["queued", "sent", "failed"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceRegistration(BaseModel):
    id: UUID
    member_id: UUID
    platform: DevicePlatform
    push_token: str
    last_seen_at: datetime


class DeviceRegistrationCreate(StrictApiModel):
    platform: DevicePlatform
    push_token: StrictStr = Field(min_length=1)


class PushNotification(BaseModel):
    id: UUID
    tenant_id: UUID
    purchase_request_id: UUID
    member_id: UUID
    status: PushNotificationStatus
    attempts: int
    created_at: datetime
    sent_at: datetime | None = None
