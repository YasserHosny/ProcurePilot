from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from procurepilot_api.config import Settings
from procurepilot_api.errors import ErrorEnvelope
from procurepilot_api.shared.logging import get_trace_id

limiter = Limiter(key_func=get_remote_address)


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
