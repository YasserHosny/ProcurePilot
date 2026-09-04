from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from uuid import uuid4

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "apikey",
        "api_key",
        "authorization",
        "credential",
        "jwt",
        "password",
        "refresh_token",
        "secret",
        "service_role_key",
        "supabase_anon_key",
        "supabase_jwt_secret",
        "supabase_service_role_key",
        "token",
    }
)
_SENSITIVE_PATTERN = re.compile(
    r"(?i)(bearer\s+)[a-z0-9._~+/=-]+|"
    r"((?:password|token|secret|apikey|api[_-]?key|authorization)=)[^\s&]+"
)

_RESERVED_LOG_RECORD_KEYS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def new_trace_id() -> str:
    return uuid4().hex


def set_trace_id(trace_id: str) -> Token[str | None]:
    return _trace_id.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    _trace_id.reset(token)


def get_trace_id() -> str:
    trace_id = _trace_id.get()
    if trace_id is None:
        trace_id = new_trace_id()
        _trace_id.set(trace_id)
    return trace_id


def redact(value: object) -> object:
    if isinstance(value, str):
        return _SENSITIVE_PATTERN.sub(_replace_secret_match, value)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def configure_logging(level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
    logging.captureWarnings(True)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": redact(record.getMessage()),
            "trace_id": get_trace_id(),
        }

        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = "[REDACTED]" if _is_sensitive_key(key) else redact(value)

        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _is_sensitive_key(key: str) -> bool:
    normalised = key.lower().replace("-", "_")
    return normalised in _SENSITIVE_KEYS or any(part in normalised for part in _SENSITIVE_KEYS)


def _replace_secret_match(match: re.Match[str]) -> str:
    if match.group(1):
        return f"{match.group(1)}[REDACTED]"
    if match.group(2):
        return f"{match.group(2)}[REDACTED]"
    return "[REDACTED]"
