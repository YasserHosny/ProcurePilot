"""Daily worker for accounting synchronization (R3.1, task T021).

Polls accounting_connection for rows due for sync (status = 'active' and last_synced_at is
null or older than 1 day). Calls SyncService.sync() for each due connection.
Concurrency protection is handled inside SyncService.sync() via PostgreSQL advisory lock,
so this worker performs a plain SELECT and relies on ConflictError to skip in-flight syncs.
"""

from __future__ import annotations

import argparse
import logging
import time
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.accounting.sync_service import SyncService

logger = logging.getLogger(__name__)


def tick(settings: Settings, sync_service: SyncService | None = None) -> dict[str, int]:
    """Execute a single polling tick across all due accounting connections.

    Queries connections where status is 'active' and last_synced_at is null or
    older than 1 day. Invokes SyncService.sync() for each candidate.
    Catches ConflictError (advisory lock already held) and skips silently with info log.
    Catches other exceptions per-connection so failure on one does not block the rest.
    """
    candidates = _find_due_connections(settings)
    stats = {
        "checked": len(candidates),
        "synced": 0,
        "skipped_conflict": 0,
        "failed": 0,
    }

    service = sync_service or SyncService()

    for candidate in candidates:
        connection_id = UUID(str(candidate["id"]))
        tenant_id = UUID(str(candidate["tenant_id"]))
        try:
            service.sync(
                settings,
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            stats["synced"] += 1
        except ConflictError:
            logger.info(
                "Sync already running for accounting connection %s; skipping",
                connection_id,
            )
            stats["skipped_conflict"] += 1
        except Exception:
            logger.exception(
                "Accounting sync failed for connection %s",
                connection_id,
            )
            stats["failed"] += 1

    return stats


def _find_due_connections(settings: Settings) -> list[dict[str, object]]:
    """Select accounting connections due for daily sync across all tenants.

    Uses service_role to query across tenants. Tenant ID is read directly from
    each returned row, never derived from any external payload.
    """
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                select c.id, c.tenant_id
                from accounting_connection c
                join tenant t on t.id = c.tenant_id
                where c.status = 'active'
                  and (c.last_synced_at is null or c.last_synced_at < now() - interval '1 day')
                order by c.last_synced_at nulls first, c.id
                """
            )
            return [dict(r) for r in cur.fetchall()]


def run_loop(
    settings: Settings,
    *,
    once: bool = False,
    interval_seconds: int = 3600,
) -> None:
    """Continuous polling loop for accounting synchronization.

    Defaults to a 1-hour interval since the 1-day last_synced_at check in the query
    enforces the daily synchronization cadence.
    """
    logger.info(
        "Starting accounting sync worker (once=%s, interval=%ss)",
        once,
        interval_seconds,
    )
    while True:
        try:
            stats = tick(settings)
            if stats["checked"]:
                logger.info("Accounting sync pass completed: %s", stats)
        except Exception:
            logger.exception("Error during accounting sync worker pass")
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Accounting synchronization worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    args = parser.parse_args()
    run_loop(get_settings(), once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
