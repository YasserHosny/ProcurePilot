"""The one place a psycopg connection is opened.

DATABASE_URL on hosted is Supabase's transaction-mode pooler (port 6543), which hands the
same backend session to many client connections. psycopg 3 auto-prepares a query after
``prepare_threshold`` (default 5) executions on one connection, naming it ``_pg3_0``,
``_pg3_1``, ... per connection; two client connections sharing a backend then collide with
``DuplicatePreparedStatement: prepared statement "_pg3_0" already exists``. Every connection
therefore disables server-side prepared statements. A guard test fails if ``psycopg.connect``
is called anywhere else in this package.
"""

from __future__ import annotations

from typing import Any

import psycopg


def connect(dsn: str | None = None, **kwargs: object) -> psycopg.Connection[Any]:
    """Open a connection with prepared statements disabled; other kwargs pass through.

    dsn defaults to the configured DATABASE_URL. Any caller-supplied
    prepare_threshold is overridden: there is no safe value behind the pooler.
    """
    if dsn is None:
        from procurepilot_api.config import get_settings

        dsn = get_settings().database_url.get_secret_value()
    kwargs["prepare_threshold"] = None
    return psycopg.connect(dsn, **kwargs)  # type: ignore[arg-type]
