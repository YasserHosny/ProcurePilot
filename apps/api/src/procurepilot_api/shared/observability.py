"""Error reporting — task T081 (FR-029).

Sentry is initialised only when a DSN is configured, so local development and tests run without
it and without a stub. An unset DSN is a valid state, not a misconfiguration: the API must start
and behave identically whether or not error reporting is switched on.
"""

from __future__ import annotations

import logging

from procurepilot_api.config import Settings

logger = logging.getLogger(__name__)


def init_error_reporting(settings: Settings) -> bool:
    """Initialise Sentry if a DSN is configured. Returns whether it was enabled."""
    dsn = settings.sentry_dsn
    if dsn is None or not dsn.get_secret_value():
        logger.info("Sentry DSN not configured; error reporting is disabled")
        return False

    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - dependency is pinned, this is belt and braces
        logger.warning("sentry-sdk is not installed; error reporting is disabled")
        return False

    sentry_sdk.init(
        dsn=dsn.get_secret_value(),
        environment=settings.api_env,
        # Tracing off by default: it costs money per event and nobody has agreed a budget or a
        # sample rate. Turn it on deliberately, not by inheriting a library default.
        traces_sample_rate=0.0,
        # Never ship request bodies or headers to a third party. This service handles supplier
        # pricing and personal data, and Principle I's provenance rules do not extend to
        # exporting the data itself.
        send_default_pii=False,
    )
    logger.info("Sentry error reporting enabled for environment %s", settings.api_env)
    return True
