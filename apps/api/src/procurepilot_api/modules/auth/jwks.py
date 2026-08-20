"""JWKS key resolution for verifying Supabase access tokens.

Supabase signs access tokens with asymmetric keys (ES256, EC P-256), publishing the public half
at `/auth/v1/.well-known/jwks.json`. The signing key rotates, so the key set is fetched at runtime
and cached rather than configured.

The shared JWT secret still exists for older or self-hosted deployments that sign with HS256, and
is kept as a fallback — but it is never a substitute for a key this module resolves. See
`verify_supabase_jwt` for why that distinction is load-bearing.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from procurepilot_api.config import Settings

logger = logging.getLogger(__name__)

# Long enough that verification is not gated on network round-trips, short enough that a rotated
# key is picked up without a restart. An unknown `kid` also forces a refresh, so this TTL governs
# routine staleness, not rotation response.
CACHE_TTL_SECONDS = 600

# Refuse to hammer the identity provider if it is failing or a caller is presenting garbage kids.
MIN_REFRESH_INTERVAL_SECONDS = 10


class JwksUnavailableError(RuntimeError):
    """The key set could not be fetched. Distinct from a token being invalid."""


class JwksCache:
    """Fetches and caches the JWKS, keyed by `kid`."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0
        self._last_attempt_at: float = 0.0

    @property
    def url(self) -> str:
        return f"{self._settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    def get_key(self, kid: str) -> dict[str, Any] | None:
        """Return the JWK for `kid`, refreshing once if it is unknown.

        An unknown kid is the expected signal that the provider rotated its signing key, so one
        forced refresh is correct. Returning None (rather than raising) lets the caller decide
        whether an unresolvable kid is an invalid token or an outage.
        """
        with self._lock:
            if self._is_stale():
                self._refresh_locked()

            key = self._keys.get(kid)
            if key is not None:
                return key

            # Unknown kid: the key set may have rotated since the last fetch.
            if self._may_retry():
                self._refresh_locked()
                key = self._keys.get(kid)

            return key

    def _is_stale(self) -> bool:
        return not self._keys or (time.monotonic() - self._fetched_at) > CACHE_TTL_SECONDS

    def _may_retry(self) -> bool:
        return (time.monotonic() - self._last_attempt_at) > MIN_REFRESH_INTERVAL_SECONDS

    def _refresh_locked(self) -> None:
        self._last_attempt_at = time.monotonic()
        client = self._client or httpx.Client(timeout=5.0)
        try:
            response = client.get(self.url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Keep serving the previous key set if we have one: a transient outage at the identity
            # provider should not sign every user out.
            logger.warning("Could not refresh JWKS from %s: %s", self.url, exc)
            if not self._keys:
                raise JwksUnavailableError(str(exc)) from exc
            return
        finally:
            if self._client is None:
                client.close()

        keys = {k["kid"]: k for k in document.get("keys", []) if k.get("kid")}
        if not keys:
            logger.warning("JWKS at %s contained no usable keys", self.url)
            if not self._keys:
                raise JwksUnavailableError("empty key set")
            return

        self._keys = keys
        self._fetched_at = time.monotonic()
        logger.info("Refreshed JWKS: %d key(s)", len(keys))


_cache: JwksCache | None = None
_cache_lock = threading.Lock()


def get_jwks_cache(settings: Settings) -> JwksCache:
    """Process-wide cache, so every request does not refetch the key set."""
    global _cache
    with _cache_lock:
        if _cache is None or _cache._settings is not settings:
            _cache = JwksCache(settings)
        return _cache


def reset_jwks_cache() -> None:
    """Drop the cached instance. For tests, and for a deliberate re-read after config changes."""
    global _cache
    with _cache_lock:
        _cache = None
