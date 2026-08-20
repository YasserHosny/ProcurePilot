"""Shared test configuration.

Settings deliberately has no defaults — every value must come from the environment, so that no
secret can hide in the source (FR-027). Tests therefore have to supply a complete environment.
These are obviously-fake local values; nothing here is a real credential.
"""

from __future__ import annotations

import os

import pytest

TEST_ENV: dict[str, str] = {
    "API_HOST": "127.0.0.1",
    "API_PORT": "8000",
    "API_ENV": "local",
    "API_LOG_LEVEL": "info",
    "API_CORS_ORIGINS": "http://localhost:4200",
    "SUPABASE_URL": "http://localhost:54321",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "SUPABASE_JWT_SECRET": "test-secret-value-not-used-anywhere-real",
    "SUPABASE_JWT_AUDIENCE": "authenticated",
    "SUPABASE_JWT_ISSUER": "http://localhost:54321/auth/v1",
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:54322/postgres",
    "PLATFORM_INVITATION_TTL_DAYS": "7",
    "MEMBER_INVITATION_TTL_DAYS": "7",
    "RATE_LIMIT_AUTH": "10/minute",
    "WEB_API_BASE_URL": "http://localhost:8000/api/v1",
    "WEB_DEFAULT_LOCALE": "en",
}


# Applied at import time, before pytest collects: importing a module that builds Settings (or a
# router that depends on one) happens during collection, which is earlier than any fixture runs.
for _key, _value in TEST_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-assert the environment per test, so one test cannot leak config into the next."""
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
