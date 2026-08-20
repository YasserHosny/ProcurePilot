from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from pydantic import BaseModel, ValidationError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import AuthenticationError
from procurepilot_api.modules.auth.jwks import JwksUnavailableError, get_jwks_cache

# Algorithms this service will verify, and nothing else.
#
# The allowlist is the security control, not a preference. A JWT header is attacker-controlled, so
# a verifier that trusts `alg` can be told which algorithm to use — the classic attacks being
# `alg: none`, and presenting an HMAC token signed with the *public* key of an asymmetric pair so
# that a verifier which picks HMAC-with-the-public-key accepts it. We therefore decide the
# verification path from the resolved KEY, never from the token's own header.
ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256"})
SYMMETRIC_ALGORITHMS = frozenset({"HS256"})
SUPPORTED_ALGORITHMS = ASYMMETRIC_ALGORITHMS | SYMMETRIC_ALGORITHMS


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


def _unverified_header(token: str) -> dict[str, Any]:
    try:
        return jwt.get_unverified_header(token)
    except JWTError as exc:
        raise AuthenticationError(details={"reason": "malformed_token"}) from exc


def _resolve_key(token: str, settings: Settings) -> tuple[Any, list[str]]:
    """Return the verification key and the algorithms permitted FOR THAT KEY.

    Returning the algorithm list alongside the key is what stops a token from choosing its own
    verification path: an asymmetric key is only ever used with asymmetric algorithms, and the
    shared secret only ever with HMAC.
    """
    header = _unverified_header(token)
    algorithm = header.get("alg")

    if algorithm not in SUPPORTED_ALGORITHMS:
        # Covers `alg: none` and anything else we have not vetted.
        raise AuthenticationError(details={"reason": "unsupported_algorithm"})

    if algorithm in ASYMMETRIC_ALGORITHMS:
        kid = header.get("kid")
        if not kid:
            raise AuthenticationError(details={"reason": "missing_key_id"})
        try:
            key = get_jwks_cache(settings).get_key(kid)
        except JwksUnavailableError as exc:
            # The provider is unreachable and we hold no keys. This is an outage, not a bad
            # token, and it must not be reported as a credential problem.
            raise AuthenticationError(details={"reason": "keys_unavailable"}) from exc
        if key is None:
            raise AuthenticationError(details={"reason": "unknown_key_id"})
        return key, sorted(ASYMMETRIC_ALGORITHMS)

    secret = settings.supabase_jwt_secret
    if secret is None:
        # An HS256 token in an environment configured only for asymmetric keys. Refusing is the
        # point: accepting it would mean verifying with whatever secret happened to be lying about.
        raise AuthenticationError(details={"reason": "symmetric_key_not_configured"})
    return secret.get_secret_value(), sorted(SYMMETRIC_ALGORITHMS)


def verify_supabase_jwt(token: str, settings: Settings | None = None) -> SupabaseClaims:
    """Verify a Supabase access token and return the claims we require.

    Supabase signs with ES256 and publishes the public keys at the JWKS endpoint; HS256 with a
    shared secret is still accepted for deployments that predate asymmetric signing keys.
    """
    active_settings = settings or get_settings()
    key, algorithms = _resolve_key(token, active_settings)

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
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
