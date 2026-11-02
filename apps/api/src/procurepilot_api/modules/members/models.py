from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.tenants.models import Tenant
from procurepilot_api.shared.display_name import DisplayName

type Locale = Literal["en", "ar"]
type MembershipStatus = Literal["active", "removed"]
type MemberInvitationStatus = Literal["pending", "accepted", "revoked", "expired"]


class Membership(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    display_name: str | None = None
    role: MemberRole
    mfa_enabled: bool
    preferred_locale: Locale | None = None
    is_active_workspace: bool
    status: MembershipStatus
    created_at: datetime | None = None


class Member(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    role: MemberRole
    status: MembershipStatus
    mfa_enabled: bool = False
    created_at: datetime | None = None


class MemberList(BaseModel):
    items: list[Member]
    next_cursor: str | None = None


class MemberUpdate(BaseModel):
    """PATCH /members/{id}: an owner changes a member's role, name, or both."""

    role: MemberRole | None = None
    display_name: DisplayName | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> MemberUpdate:
        if self.role is None and self.display_name is None:
            raise ValueError("role or display_name is required")
        return self


class MemberInvitation(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    role: MemberRole
    status: MemberInvitationStatus
    expires_at: datetime
    token: str | None = None
    email_delivery: Literal["sent", "not_configured", "failed"] | None = None


class MemberInvitationList(BaseModel):
    items: list[MemberInvitation]


class MemberInvitationCreate(BaseModel):
    email: str
    role: MemberRole
    display_name: DisplayName | None = None


class MemberInvitationAccept(BaseModel):
    token: str = Field(min_length=32)
    password: str | None = Field(default=None, min_length=12)


class Me(BaseModel):
    id: UUID
    membership_id: UUID | None = None
    email: str
    display_name: str | None = None
    role: MemberRole
    preferred_locale: Locale | None = None
    mfa_enabled: bool
    tenant: Tenant


class MeUpdate(BaseModel):
    preferred_locale: Locale | None = None
    display_name: DisplayName | None = None


class WorkspaceSummary(BaseModel):
    tenant_id: UUID
    name: str
    role: MemberRole
    is_active: bool


class WorkspaceList(BaseModel):
    items: list[WorkspaceSummary]


class ActiveWorkspaceRequest(BaseModel):
    tenant_id: UUID
    refresh_token: str | None = None


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int | None = None
    user: Me
