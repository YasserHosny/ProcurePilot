"""JWT verification — task T034.

Every case here is a token that must be REFUSED. A verifier that accepts any of them turns
tenancy into a suggestion, since `tenant_id` is read straight from the token.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from jose import jwt

from procurepilot_api.config import Settings
from procurepilot_api.errors import AuthenticationError
from procurepilot_api.modules.auth.jwt import verify_supabase_jwt

SECRET = "test-secret-value-not-used-anywhere-real"
ISSUER = "http://localhost:54321/auth/v1"
AUDIENCE = "authenticated"


@pytest.fixture
def settings() -> Settings:
    """Built from the environment conftest supplies — Settings has no defaults by design."""
    return Settings()


def make_token(secret: str = SECRET, **overrides: object) -> str:
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "member_role": "owner",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


def test_accepts_a_well_formed_token(settings: Settings) -> None:
    claims = verify_supabase_jwt(make_token(), settings)
    assert claims.member_role == "owner"
    assert claims.tenant_id is not None


def test_rejects_a_forged_signature(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(make_token(secret="attacker-chosen-secret"), settings)


def test_rejects_an_expired_token(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(make_token(exp=int(time.time()) - 60), settings)


def test_rejects_the_wrong_audience(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(make_token(aud="some-other-service"), settings)


def test_rejects_the_wrong_issuer(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(make_token(iss="https://evil.example"), settings)


def test_rejects_a_token_with_no_tenant_claim(settings: Settings) -> None:
    """A token without tenant_id must not resolve to some default workspace."""
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "member_role": "owner",
            "aud": AUDIENCE,
            "iss": ISSUER,
            "exp": int(time.time()) + 3600,
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(token, settings)


def test_rejects_an_unknown_member_role(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(make_token(member_role="superuser"), settings)


def test_ignores_the_postgrest_role_claim(settings: Settings) -> None:
    """`role` belongs to Postgres/PostgREST; the member's role travels as `member_role`.

    Regression test for a real defect: the auth hook originally wrote the member role into
    `role`, which would have made PostgREST issue `set role owner` and fail every request.
    """
    claims = verify_supabase_jwt(make_token(role="authenticated", member_role="buyer"), settings)
    assert claims.member_role == "buyer"
    assert not hasattr(claims, "role")
