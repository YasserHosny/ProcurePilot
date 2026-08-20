"""JWT verification — task T034, extended for JWKS/ES256.

Most cases here are tokens that must be REFUSED. A verifier that accepts any of them turns
tenancy into a suggestion, since `tenant_id` is read straight from the token.

The algorithm-confusion cases matter most. A JWT header is attacker-controlled: if the verifier
lets the token pick the verification path, an attacker can present an HMAC token signed with the
*public* key of the asymmetric pair, and a naive verifier will happily check it against that same
public key and accept it. These tests exist to fail loudly if that path ever opens.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt
from jose.utils import base64url_encode

from procurepilot_api.config import Settings
from procurepilot_api.errors import AuthenticationError
from procurepilot_api.modules.auth import jwks as jwks_module
from procurepilot_api.modules.auth.jwt import (
    ASYMMETRIC_ALGORITHMS,
    SYMMETRIC_ALGORITHMS,
    _resolve_key,
    verify_supabase_jwt,
)

SECRET = "test-secret-value-not-used-anywhere-real"
ISSUER = "http://localhost:54321/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-id"


@pytest.fixture
def settings() -> Settings:
    """Built from the environment conftest supplies — Settings has no defaults by design."""
    return Settings()


@pytest.fixture
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def jwks_document(ec_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    numbers = ec_key.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "EC",
                "crv": "P-256",
                "alg": "ES256",
                "use": "sig",
                "kid": KID,
                "x": base64url_encode(numbers.x.to_bytes(32, "big")).decode(),
                "y": base64url_encode(numbers.y.to_bytes(32, "big")).decode(),
            }
        ]
    }


@pytest.fixture(autouse=True)
def _served_jwks(monkeypatch: pytest.MonkeyPatch, jwks_document: dict[str, Any]) -> None:
    """Serve the key set without a network call, and isolate the process-wide cache per test."""
    jwks_module.reset_jwks_cache()

    def fake_refresh(self: jwks_module.JwksCache) -> None:
        self._last_attempt_at = time.monotonic()
        self._keys = {k["kid"]: k for k in jwks_document["keys"]}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr(jwks_module.JwksCache, "_refresh_locked", fake_refresh)
    yield
    jwks_module.reset_jwks_cache()


def claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "member_role": "owner",
        "role": "authenticated",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
    }
    base.update(overrides)
    return base


def to_pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def es256_token(key: ec.EllipticCurvePrivateKey, kid: str = KID, **overrides: object) -> str:
    return jwt.encode(claims(**overrides), to_pem(key), algorithm="ES256", headers={"kid": kid})


def hs256_token(secret: str = SECRET, **overrides: object) -> str:
    return jwt.encode(claims(**overrides), secret, algorithm="HS256")


# --- the happy paths ---------------------------------------------------------


def test_accepts_an_es256_token_verified_via_jwks(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    result = verify_supabase_jwt(es256_token(ec_key), settings)
    assert result.member_role == "owner"
    assert result.tenant_id is not None


def test_still_accepts_hs256_for_deployments_using_a_shared_secret(settings: Settings) -> None:
    result = verify_supabase_jwt(hs256_token(), settings)
    assert result.member_role == "owner"


# --- algorithm confusion -----------------------------------------------------
#
# These assert the CONTROL directly, on _resolve_key, rather than only asserting that a forged
# token is rejected. That distinction was earned: an earlier version of this file tested only
# rejection, and it passed unchanged when the algorithm binding was deliberately removed — the
# forged tokens happened to fail for unrelated reasons. A test that cannot fail when the control
# is gone is not testing the control.


def test_an_asymmetric_header_can_only_ever_use_asymmetric_algorithms(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    """The key resolved from JWKS must never be offered to an HMAC algorithm."""
    _key, algorithms = _resolve_key(es256_token(ec_key), settings)
    assert set(algorithms) == set(ASYMMETRIC_ALGORITHMS)
    assert not set(algorithms) & set(SYMMETRIC_ALGORITHMS), (
        "a JWKS public key must not be usable as an HMAC secret — that is the confusion attack"
    )


def test_a_symmetric_header_can_only_ever_use_symmetric_algorithms(settings: Settings) -> None:
    _key, algorithms = _resolve_key(hs256_token(), settings)
    assert set(algorithms) == set(SYMMETRIC_ALGORITHMS)
    assert not set(algorithms) & set(ASYMMETRIC_ALGORITHMS)


def test_an_unvetted_algorithm_is_refused_before_any_key_is_resolved(settings: Settings) -> None:
    """The allowlist gate must reject before key resolution, not rely on the library declining."""
    # Assembled by hand rather than signed: _resolve_key only reads the header, and the point is
    # that an algorithm we have not vetted is refused before any key is fetched.
    raw_header = json.dumps({"alg": "HS512", "kid": KID, "typ": "JWT"}).encode()
    header = base64url_encode(raw_header).decode()
    body = base64url_encode(json.dumps(claims()).encode()).decode()
    token = f"{header}.{body}.c2lnbmF0dXJl"
    with pytest.raises(AuthenticationError) as caught:
        _resolve_key(token, settings)
    assert caught.value.details["reason"] == "unsupported_algorithm"



def test_rejects_alg_none(settings: Settings) -> None:
    header = base64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode()
    body = base64url_encode(json.dumps(claims()).encode()).decode()
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(f"{header}.{body}.", settings)


def test_rejects_an_hmac_token_signed_with_the_public_key(
    settings: Settings, jwks_document: dict[str, Any]
) -> None:
    """The classic confusion attack: HMAC the token using the published public key as the secret.

    It must fail because the verification path is chosen from the RESOLVED KEY, not the header —
    an HS256 header can never reach the JWKS key.
    """
    public_material = json.dumps(jwks_document["keys"][0])
    forged = jwt.encode(claims(), public_material, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(forged, settings)


def test_rejects_an_es256_token_with_no_key_id(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    """A kid-less asymmetric token must be refused, not resolved against whatever key is cached.

    Asserted on the reason, not merely on rejection: signing this token with the correct key means
    a 'just try the only cached key' fallback would verify it happily, and a test that only
    checked for rejection would not notice.
    """
    token = jwt.encode(claims(), to_pem(ec_key), algorithm="ES256")
    with pytest.raises(AuthenticationError) as caught:
        _resolve_key(token, settings)
    assert caught.value.details["reason"] == "missing_key_id"

    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(token, settings)


def test_rejects_an_unknown_key_id(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(ec_key, kid="not-a-key-we-know"), settings)


def test_rejects_a_token_signed_by_a_different_key(settings: Settings) -> None:
    """Right kid, wrong private key — the signature must not verify."""
    impostor = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(impostor), settings)


# --- claim validation --------------------------------------------------------


def test_rejects_a_forged_hmac_signature(settings: Settings) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(hs256_token(secret="attacker-chosen-secret"), settings)


def test_rejects_an_expired_token(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(ec_key, exp=int(time.time()) - 60), settings)


def test_rejects_the_wrong_audience(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(ec_key, aud="some-other-service"), settings)


def test_rejects_the_wrong_issuer(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(ec_key, iss="https://evil.example"), settings)


def test_rejects_a_token_with_no_tenant_claim(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    """A token without tenant_id must not resolve to some default workspace."""
    payload = claims()
    del payload["tenant_id"]
    token = jwt.encode(payload, to_pem(ec_key), algorithm="ES256", headers={"kid": KID})
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(token, settings)


def test_rejects_an_unknown_member_role(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    with pytest.raises(AuthenticationError):
        verify_supabase_jwt(es256_token(ec_key, member_role="superuser"), settings)


def test_ignores_the_postgrest_role_claim(
    settings: Settings, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    """`role` belongs to Postgres/PostgREST; the member's role travels as `member_role`.

    Regression test for a real defect: the auth hook originally wrote the member role into
    `role`, which would have made PostgREST issue `set role owner` and fail every request.
    """
    result = verify_supabase_jwt(
        es256_token(ec_key, role="authenticated", member_role="buyer"), settings
    )
    assert result.member_role == "buyer"
    assert not hasattr(result, "role")
