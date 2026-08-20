from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import AuthenticationError
from procurepilot_api.modules.auth.jwt import MemberRole, verify_supabase_jwt

_bearer = HTTPBearer(auto_error=False)


class CurrentMember(BaseModel):
    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    role: MemberRole


class _TenantRecord(BaseModel):
    id: UUID


class _MembershipRecord(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    role: MemberRole
    status: str


def current_member(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentMember:
    return resolve_member_from_token(bearer_token(credentials), settings)


def bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError(details={"reason": "missing_bearer_token"})
    return credentials.credentials


def resolve_member_from_token(token: str, settings: Settings) -> CurrentMember:
    claims = verify_supabase_jwt(token, settings)
    client = _authenticated_client(settings, token)

    tenant = _fetch_one_tenant(client, claims.tenant_id)
    membership = _fetch_one_active_membership(client, claims.tenant_id, claims.sub)

    if tenant.id != membership.tenant_id or membership.role != claims.member_role:
        raise AuthenticationError(details={"reason": "membership_claim_mismatch"})

    return CurrentMember(
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        email=membership.email,
        role=membership.role,
    )


def _authenticated_client(settings: Settings, bearer_token: str) -> Client:
    client = create_client(settings.supabase_url, settings.supabase_anon_key.get_secret_value())
    client.postgrest.auth(bearer_token)
    return client


def _fetch_one_tenant(client: Client, tenant_id: UUID) -> _TenantRecord:
    response = client.table("tenant").select("id").eq("id", str(tenant_id)).limit(2).execute()
    rows = _response_rows(response.data)
    if len(rows) != 1:
        raise AuthenticationError(details={"reason": "workspace_not_resolved"})
    return _TenantRecord.model_validate(rows[0])


def _fetch_one_active_membership(
    client: Client,
    tenant_id: UUID,
    user_id: UUID,
) -> _MembershipRecord:
    response = (
        client.table("membership")
        .select("id,tenant_id,user_id,email,role,status")
        .eq("tenant_id", str(tenant_id))
        .eq("user_id", str(user_id))
        .eq("status", "active")
        .limit(2)
        .execute()
    )
    rows = _response_rows(response.data)
    if len(rows) != 1:
        raise AuthenticationError(details={"reason": "active_membership_not_found"})
    return _MembershipRecord.model_validate(rows[0])


def _response_rows(data: object) -> list[object]:
    if isinstance(data, list):
        return data
    raise AuthenticationError(details={"reason": "invalid_database_response"})
