from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from procurepilot_api.modules.auth.jwt import MemberRole

type Locale = Literal["en", "ar"]
type PlatformInvitationStatus = Literal["pending", "spent", "revoked", "expired"]


class ReferenceOption(BaseModel):
    code: str
    label_en: str
    label_ar: str


class ConfigOptions(BaseModel):
    regions: list[ReferenceOption]
    currencies: list[ReferenceOption]
    tax_models: list[ReferenceOption]


class Tenant(BaseModel):
    id: UUID
    name: str
    slug: str
    region: str
    currency: str
    tax_model: str
    default_locale: Locale
    reporting_timezone: str = "UTC"
    created_at: datetime | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_locale: Locale | None = None
    reporting_timezone: str | None = None

    @field_validator("reporting_timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Invalid IANA timezone: {v}") from e
        return v


class PlatformInvitation(BaseModel):
    id: UUID
    email: str
    token_hash: str
    expires_at: datetime
    status: PlatformInvitationStatus
    spent_at: datetime | None = None
    created_at: datetime | None = None


class SignupRequest(BaseModel):
    invitation_token: str = Field(min_length=32)
    email: str
    password: str = Field(min_length=12)
    business_name: str = Field(min_length=1, max_length=200)
    region: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_model: str
    default_locale: Locale = "en"


class WorkspaceCreated(BaseModel):
    tenant: Tenant
    membership_id: UUID
    user_id: UUID
    email: str
    role: MemberRole
    preferred_locale: Locale | None = None
    mfa_enabled: bool = False


class TenantRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    region: str
    currency: str
    tax_model: str
    default_locale: Locale
    reporting_timezone: str = "UTC"
    created_at: datetime | None = None
