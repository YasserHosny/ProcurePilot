from __future__ import annotations

import argparse
import logging
import time
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.ingestion.orchestrator import process_inbound_email

logger = logging.getLogger(__name__)

# T012: polls `ingestion_jobs` for job_type = 'email_ingest' via FOR UPDATE SKIP LOCKED —
# identical worker-queue shape to report_scheduler, export_worker, and digest_worker (R7: no
# Redis for THIS queue, database-backed only). `tenant_id` is read from the claimed job ROW, not
# from its payload — the same untrusted-payload discipline export_worker/digest_worker already
# established: the payload only carries the raw-email storage path, a hint the worker verifies
# nothing sensitive against, since tenant_id never comes from it.


def tick(settings: Settings) -> dict[str, int]:
    stats = {"claimed": 0, "completed": 0, "duplicate": 0, "rejected": 0, "failed": 0}
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        claimed = _claim_pending_jobs(conn)
        stats["claimed"] = len(claimed)
        conn.commit()

    for job in claimed:
        outcome = _process_job(settings, job)
        stats[outcome] = stats.get(outcome, 0) + 1

    return stats


def _claim_pending_jobs(conn: psycopg.Connection, limit: int = 10) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select * from ingestion_jobs
            where job_type = 'email_ingest'
              and status = 'pending'
            order by created_at
            limit %s
            for update skip locked
            """,
            (limit,),
        )
        jobs = [dict(r) for r in cur.fetchall()]
        for job in jobs:
            cur.execute(
                """
                update ingestion_jobs
                set status = 'processing', locked_by = %s, locked_at = now(), updated_at = now()
                where id = %s
                """,
                ("email_ingestion_worker", job["id"]),
            )
    return jobs


def _process_job(settings: Settings, job: dict[str, object]) -> str:
    job_id = UUID(str(job["id"]))
    tenant_id = UUID(str(job["tenant_id"]))
    payload = job.get("payload") or {}
    raw_email_path = payload.get("raw_email_path") if isinstance(payload, dict) else None

    try:
        raw_email_bytes = _fetch_raw_email(settings, raw_email_path)
        result = process_inbound_email(
            settings,
            tenant_id=tenant_id,
            raw_email_bytes=raw_email_bytes,
            raw_email_ref=raw_email_path,
        )
        _mark_job_completed(settings, job_id)
        return str(result.get("status", "completed"))
    except Exception as exc:
        logger.exception("Email ingestion job %s failed", job_id)
        _mark_job_failed(settings, job_id, attempts=int(job["attempts"]),
                          max_attempts=int(job["max_attempts"]), error=str(exc))
        return "failed"


def _fetch_raw_email(settings: Settings, raw_email_path: str | None) -> bytes:
    if not raw_email_path:
        raise ValueError("job payload missing raw_email_path")
    client = create_client(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
    return bytes(client.storage.from_(settings.ingestion_raw_bucket).download(raw_email_path))


def _mark_job_completed(settings: Settings, job_id: UUID) -> None:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update ingestion_jobs
                set status = 'completed', completed_at = now(), updated_at = now()
                where id = %s
                """,
                (job_id,),
            )
        conn.commit()


def _mark_job_failed(
    settings: Settings, job_id: UUID, *, attempts: int, max_attempts: int, error: str
) -> None:
    new_attempts = attempts + 1
    next_status = "pending" if new_attempts < max_attempts else "failed"
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update ingestion_jobs
                set status = %s, attempts = %s, last_error = %s, locked_by = null,
                    locked_at = null, updated_at = now(),
                    completed_at = case when %s = 'failed' then now() else null end
                where id = %s
                """,
                (next_status, new_attempts, error[:2000], next_status, job_id),
            )
        conn.commit()


def run_loop(settings: Settings, *, once: bool = False, interval_seconds: int = 10) -> None:
    logger.info("Starting email ingestion worker (once=%s, interval=%ss)", once, interval_seconds)
    while True:
        try:
            stats = tick(settings)
            if stats["claimed"]:
                logger.info("Email ingestion pass completed: %s", stats)
        except Exception:
            logger.exception("Error during email ingestion worker pass")
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=10)
    args = parser.parse_args()
    run_loop(get_settings(), once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
