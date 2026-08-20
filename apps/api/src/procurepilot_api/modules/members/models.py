from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.tenants.models import Tenant

type Locale = Literal["en", "ar"]
type MembershipStatus = Literal["active", "removed"]
type MemberInvitationStatus = Literal["pending", "accepted", "revoked", "expired"]


class Membership(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    role: MemberRole
    mfa_enabled: bool
    preferred_locale: Locale | None = None
    is_active_workspace: bool
    status: MembershipStatus
    created_at: datetime | None = None


class Member(BaseModel):
    id: UUID
    email: str
    role: MemberRole
    status: MembershipStatus
    mfa_enabled: bool = False
    created_at: datetime | None = None


class MemberList(BaseModel):
    items: list[Member]
    next_cursor: str | None = None


class MemberRoleUpdate(BaseModel):
    role: MemberRole


class MemberInvitation(BaseModel):
    id: UUID
    email: str
    role: MemberRole
    status: MemberInvitationStatus
    expires_at: datetime
    token: str | None = None


class MemberInvitationList(BaseModel):
    items: list[MemberInvitation]


class MemberInvitationCreate(BaseModel):
    email: str
    role: MemberRole


class MemberInvitationAccept(BaseModel):
    token: str = Field(min_length=32)
    password: str | None = Field(default=None, min_length=12)


class Me(BaseModel):
    id: UUID
    email: str
    role: MemberRole
    preferred_locale: Locale | None = None
    mfa_enabled: bool
    tenant: Tenant


class MeUpdate(BaseModel):
    preferred_locale: Locale | None = None


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
