from __future__ import annotations

from collections.abc import Awaitable, Callable

from procurepilot_logging import (
    configure_logging,
    get_trace_id,
    new_trace_id,
    redact,
    reset_trace_id,
    set_trace_id,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

__all__ = [
    "TraceIdMiddleware",
    "configure_logging",
    "get_trace_id",
    "new_trace_id",
    "redact",
    "reset_trace_id",
    "set_trace_id",
]

TRACE_ID_HEADER = "X-Trace-Id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_trace_id = request.headers.get(TRACE_ID_HEADER)
        trace_id = incoming_trace_id.strip() if incoming_trace_id else new_trace_id()
        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
            response.headers[TRACE_ID_HEADER] = trace_id
            return response
        finally:
            reset_trace_id(token)
