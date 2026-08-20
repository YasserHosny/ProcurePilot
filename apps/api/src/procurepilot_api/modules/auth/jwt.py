from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from pydantic import BaseModel, ValidationError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import AuthenticationError


class MemberRole(StrEnum):
    owner = "owner"
    buyer = "buyer"
    branch_manager = "branch_manager"
    approver = "approver"
    viewer = "viewer"


class SupabaseClaims(BaseModel):
    """Claims we require from a Supabase-issued access token.

    `member_role` — NOT `role` — carries the ProcurePilot role. Supabase and PostgREST reserve
    the `role` claim for the Postgres role to assume for the request (`authenticated`, `anon`,
    `service_role`); putting 'owner' there makes PostgREST run `set role owner`, which fails with
    'role "owner" does not exist'. The auth hook in migration 0006 keeps the two separate.
    """

    sub: UUID
    tenant_id: UUID
    member_role: MemberRole
    aud: str
    iss: str
    exp: int


def verify_supabase_jwt(token: str, settings: Settings | None = None) -> SupabaseClaims:
    active_settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            active_settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=active_settings.supabase_jwt_audience,
            issuer=active_settings.supabase_jwt_issuer,
            options={
                "require_aud": True,
                "require_exp": True,
                "require_iss": True,
                "require_sub": True,
            },
        )
        return SupabaseClaims.model_validate(payload)
    except ExpiredSignatureError as exc:
        raise AuthenticationError(details={"reason": "expired_token"}) from exc
    except JWTClaimsError as exc:
        raise AuthenticationError(details={"reason": "invalid_token_claims"}) from exc
    except (JWTError, ValidationError) as exc:
        raise AuthenticationError(details={"reason": "invalid_token"}) from exc
