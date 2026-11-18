"""Request context captured with a feedback submission (spec 025, research D3).

The system sets workspace, submitter, role, demo flag, timestamp and app version. The page
address and language can only come from the browser, so they are taken from the standard
`Referer` and `Accept-Language` headers, validated here, and used for triage context only.
Nothing in this module affects authorisation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal
from urllib.parse import urlsplit

from procurepilot_api.config import Settings

type FeedbackLocale = Literal["en", "ar"]

MAX_PAGE_PATH_CHARS = 2000
_SUPPORTED_LOCALES: tuple[FeedbackLocale, ...] = ("en", "ar")


def _as_locale(value: object) -> FeedbackLocale | None:
    for locale in _SUPPORTED_LOCALES:
        if value == locale:
            return locale
    return None


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_ACCEPT_LANGUAGE_CHARS = 1000
_MAX_ACCEPT_LANGUAGE_ITEMS = 20


def _origin(value: str) -> str | None:
    """`scheme://host[:port]` lower-cased, or None when `value` is not an absolute http(s) URL."""
    try:
        parts = urlsplit(value.strip())
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    host = f"[{hostname}]" if ":" in hostname else hostname
    authority = f"{host}:{port}" if port is not None else host
    return f"{parts.scheme.lower()}://{authority}".lower()


def allowed_web_origins(settings: Settings) -> tuple[str, ...]:
    """Origins the web app is served from: WEB_ORIGIN, WEB_PUBLIC_URL, then the CORS origins."""
    candidates: list[str] = []
    if settings.web_origin:
        candidates.append(settings.web_origin)
    if settings.web_public_url:
        candidates.append(settings.web_public_url)
    candidates.extend(settings.api_cors_origins)
    origins: list[str] = []
    for candidate in candidates:
        origin = _origin(candidate)
        if origin is not None and origin not in origins:
            origins.append(origin)
    return tuple(origins)


def page_path_from_referer(referer: str | None, allowed_origins: Iterable[str]) -> str:
    """Path plus query of a same-origin Referer, capped at 2000 characters; "" otherwise.

    A foreign or malformed Referer is treated as absent, not as an error: feedback must still
    go through. The fragment is dropped and control characters are removed.
    """
    if not referer:
        return ""
    allowed = {origin.lower() for origin in allowed_origins}
    origin = _origin(referer)
    if origin is None or origin not in allowed:
        return ""
    try:
        parts = urlsplit(referer.strip())
    except ValueError:
        return ""
    path = parts.path or "/"
    value = f"{path}?{parts.query}" if parts.query else path
    value = _CONTROL_CHARS.sub("", value)
    return value[:MAX_PAGE_PATH_CHARS]


def locale_from_accept_language(header: str | None, default: str | None) -> FeedbackLocale:
    """The best-ranked supported language in `Accept-Language`, else `default`, else "en"."""
    fallback: FeedbackLocale = _as_locale(default) or "en"
    if not header:
        return fallback
    ranked: list[tuple[float, int, FeedbackLocale]] = []
    items = header[:_MAX_ACCEPT_LANGUAGE_CHARS].split(",")[:_MAX_ACCEPT_LANGUAGE_ITEMS]
    for position, item in enumerate(items):
        tag, *params = (piece.strip() for piece in item.split(";"))
        primary = _as_locale(tag.split("-", 1)[0].lower())
        if primary is None:
            continue
        quality = 1.0
        for param in params:
            name, _, raw = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(raw)
                except ValueError:
                    quality = 1.0
        if quality <= 0:
            continue
        ranked.append((-quality, position, primary))
    if not ranked:
        return fallback
    ranked.sort()
    return ranked[0][2]
