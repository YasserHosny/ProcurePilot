from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import AuthenticationError, ErrorEnvelope
from procurepilot_api.modules.auth.jwt import verify_supabase_jwt
from procurepilot_api.shared.logging import get_trace_id

limiter = Limiter(key_func=get_remote_address)


def tenant_member_rate_limit_key(request: Request) -> str:
    """Key mutation-endpoint rate limits by verified tenant + member claims (FR-020), not raw
    IP: an office NAT'd behind one address must not share a single bucket across members, and
    one tenant's traffic must not be able to exhaust another tenant's budget. Falls back to IP
    when there's no valid bearer token — the endpoint's own auth dependency still rejects the
    request, but slowapi needs a key to check before that dependency runs.

    There's no `membership_id` claim on the token itself (see SupabaseClaims) — `sub` (the
    Supabase user id) combined with the verified `tenant_id` already uniquely identifies "this
    member in this tenant" for keying purposes, without an extra DB round-trip on every request
    just to resolve the exact membership row.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[len("bearer ") :]
        try:
            claims = verify_supabase_jwt(token, get_settings())
        except AuthenticationError:
            pass
        else:
            return f"{claims.tenant_id}:{claims.sub}"
    return get_remote_address(request)


mutation_limiter = Limiter(key_func=tenant_member_rate_limit_key)


def configure_rate_limiting(app: FastAPI, _settings: Settings) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


async def _rate_limit_handler(_request: Request, _exc: Exception) -> JSONResponse:
    envelope = ErrorEnvelope(
        code="rate_limit.exceeded",
        message="Too many requests.",
        details=None,
        trace_id=get_trace_id(),
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=envelope.model_dump(mode="json"),
    )


def auth_rate_limit(settings: Settings) -> str:
    return settings.rate_limit_auth
