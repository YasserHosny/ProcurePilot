from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.exports.storage import ExportStorage
from procurepilot_api.modules.reports.schedules import (
    derive_weekly_window,
)
from procurepilot_api.modules.reports.schedules import (
    next_run_at as compute_next_run_at,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

logger = logging.getLogger(__name__)


def tick(settings: Settings) -> dict[str, int]:
    """Execute one scheduler pass: claim due schedules, enqueue runs, and purge
    expired artifacts.
    """
    stats = {"claimed": 0, "enqueued": 0, "purged": 0}
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        claimed = _claim_due_schedules(conn)
        stats["claimed"] = len(claimed)

        for schedule in claimed:
            enqueued = _process_due_schedule(conn, settings, schedule)
            if enqueued:
                stats["enqueued"] += 1
        conn.commit()

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        purged = _purge_expired_artifacts(conn, settings)
        stats["purged"] = purged
        conn.commit()

    return stats


def _claim_due_schedules(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Claim active report schedules whose next_run_at is due via FOR UPDATE SKIP LOCKED."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select s.*, coalesce(t.reporting_timezone, 'UTC') as reporting_timezone
            from report_schedule s
            join tenant t on t.id = s.tenant_id
            where s.status = 'active'
              and s.next_run_at <= now()
            order by s.next_run_at
            limit 50
            for update of s skip locked
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _process_due_schedule(
    conn: psycopg.Connection,
    settings: Settings,
    schedule: dict[str, Any],
) -> bool:
    """Derive window, advance next_run_at, write snapshot, and enqueue export_job."""
    tz_str = str(schedule.get("reporting_timezone") or "UTC")
    due_at = schedule["next_run_at"]
    if isinstance(due_at, str):
        due_at = datetime.fromisoformat(due_at)

    window = derive_weekly_window(due_at, timezone=tz_str)
    new_next_run = compute_next_run_at(
        int(schedule["weekday"]),
        after=due_at,
        timezone=tz_str,
    )

    raw_filters = schedule["filters"]
    if isinstance(raw_filters, str):
        filters_dict = json.loads(raw_filters)
    else:
        filters_dict = dict(raw_filters)

    filters_dict["period_start"] = str(window.period_start)
    filters_dict["period_end"] = str(window.period_end)

    snapshot = {
        "schedule_id": str(schedule["id"]),
        "kind": schedule["kind"],
        "format": schedule["format"],
        "filters": filters_dict,
        "weekday": schedule["weekday"],
        "locale": schedule.get("locale") or "en",
        "rule_version": schedule.get("rule_version") or "",
        "period_start": str(window.period_start),
        "period_end": str(window.period_end),
    }

    job_id = uuid4()
    with conn.cursor(row_factory=dict_row) as cur:
        # Update schedule next_run_at and last_run_at
        cur.execute(
            """
            update report_schedule
            set last_run_at = now(),
                next_run_at = %s,
                updated_at = now()
            where id = %s
            """,
            (new_next_run, schedule["id"]),
        )

        # Idempotent insert: per-period unique index prevents duplicate enqueues
        cur.execute(
            """
            insert into export_job
              (id, tenant_id, requested_by, kind, format, filters, status,
               schedule_id, schedule_snapshot, locale, rule_version)
            values (%s, %s, %s, %s, %s, %s, 'queued', %s, %s, %s, %s)
            on conflict (tenant_id, schedule_id, (filters->>'period_start'))
              where schedule_id is not null
            do nothing
            returning id
            """,
            (
                job_id,
                schedule["tenant_id"],
                schedule["created_by_membership_id"],
                schedule["kind"],
                schedule["format"],
                Jsonb(filters_dict),
                schedule["id"],
                Jsonb(snapshot),
                schedule.get("locale") or "en",
                schedule.get("rule_version") or "",
            ),
        )
        row = cur.fetchone()

    if row is None:
        logger.info(
            "Schedule %s already generated for period %s",
            schedule["id"],
            window.period_start,
        )
        return False

    _enqueue_job(settings, job_id, UUID(str(schedule["tenant_id"])))

    # Record run_enqueued audit event
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=UUID(str(schedule["tenant_id"])),
            actor_membership_id=UUID(str(schedule["created_by_membership_id"])),
            actor_email="system@procurepilot.local",
            action="reports.run_enqueued",
            target={
                "export_job_id": str(job_id),
                "schedule_id": str(schedule["id"]),
                "kind": schedule["kind"],
                "period_start": str(window.period_start),
                "period_end": str(window.period_end),
            },
            outcome="success",
            trace_id=get_trace_id(),
        )
    )
    return True


def _enqueue_job(settings: Settings, job_id: UUID, tenant_id: UUID) -> None:
    try:
        from redis import Redis
        from rq import Queue

        queue = Queue(settings.export_queue_name, connection=Redis.from_url(settings.redis_url))
        queue.enqueue(
            "procurepilot_api.workers.export_worker.process_export_job",
            {"job_id": str(job_id), "tenant_id": str(tenant_id)},
            job_id=str(job_id),
        )
    except Exception as exc:
        logger.warning("Failed to enqueue export job %s to Redis/RQ: %s", job_id, exc)


def _purge_expired_artifacts(conn: psycopg.Connection, settings: Settings) -> int:
    """Purge artifacts that exceeded retention: delete storage files, flip status
    to expired, and audit.
    """
    purged_count = 0
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, requested_by, kind, format, storage_bucket, storage_path
            from export_job
            where status = 'completed'
              and expires_at is not null
              and expires_at <= now()
            limit 100
            for update skip locked
            """
        )
        expired_jobs = [dict(r) for r in cur.fetchall()]

        storage = ExportStorage(settings)
        for job in expired_jobs:
            if job.get("storage_bucket") and job.get("storage_path"):
                storage.delete_object(
                    bucket=str(job["storage_bucket"]),
                    path=str(job["storage_path"]),
                )

            cur.execute(
                """
                update export_job
                set status = 'expired',
                    storage_bucket = null,
                    storage_path = null,
                    download_url = null
                where id = %s
                """,
                (job["id"],),
            )
            purged_count += 1

            get_audit_writer().record(
                AuditEventCreate(
                    tenant_id=UUID(str(job["tenant_id"])),
                    actor_membership_id=(
                        UUID(str(job["requested_by"])) if job.get("requested_by") else None
                    ),
                    actor_email="system@procurepilot.local",
                    action="reports.artifact_purged",
                    target={
                        "export_job_id": str(job["id"]),
                        "kind": str(job["kind"]),
                        "format": str(job["format"]),
                    },
                    outcome="success",
                    trace_id=get_trace_id(),
                )
            )

    return purged_count


def run_loop(settings: Settings, *, once: bool = False, interval_seconds: int = 60) -> None:
    logger.info("Starting report scheduler worker (once=%s, interval=%ss)", once, interval_seconds)
    while True:
        try:
            stats = tick(settings)
            logger.info("Scheduler pass completed: %s", stats)
        except Exception as exc:
            logger.error("Error during scheduler pass: %s", exc, exc_info=True)
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="ProcurePilot report scheduler worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scheduler tick pass and exit immediately",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between scheduler passes when running continuously",
    )
    args = parser.parse_args()

    settings = get_settings()
    run_loop(settings, once=args.once, interval_seconds=args.interval)


if __name__ == "__main__":
    main()
