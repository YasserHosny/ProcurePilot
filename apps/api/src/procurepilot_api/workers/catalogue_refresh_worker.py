"""Create reviewable catalogue previews from scheduled CSV refresh jobs."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.catalogue.connector import CsvCatalogueConnector

logger = logging.getLogger(__name__)


def tick(settings: Settings) -> dict[str, int]:
    stats = {"claimed": 0, "completed": 0, "failed": 0}
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        jobs = _claim_jobs(conn)
        stats["claimed"] = len(jobs)
        conn.commit()

    for job in jobs:
        try:
            review_id = _create_review(settings, job)
            _mark_completed(settings, UUID(str(job["id"])), review_id)
            stats["completed"] += 1
        except Exception as exc:
            logger.exception("Catalogue refresh job %s failed", job["id"])
            _mark_failed(
                settings,
                UUID(str(job["id"])),
                attempts=int(job["attempts"]),
                max_attempts=int(job["max_attempts"]),
                error=str(exc),
            )
            stats["failed"] += 1
    return stats


def _claim_jobs(conn: psycopg.Connection, *, limit: int = 10) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("set local role service_role")
        cur.execute(
            """
            select * from ingestion_jobs
            where job_type = 'catalogue_import'
              and status = 'pending'
            order by created_at, id
            limit %s
            for update skip locked
            """,
            (limit,),
        )
        jobs = [dict(row) for row in cur.fetchall()]
        for job in jobs:
            cur.execute(
                """
                update ingestion_jobs
                set status = 'processing', locked_by = 'catalogue_refresh_worker',
                    locked_at = now(), updated_at = now()
                where id = %s
                returning *
                """,
                (job["id"],),
            )
        return jobs


def _create_review(settings: Settings, job: dict[str, Any]) -> UUID:
    payload = job.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("catalogue refresh payload must be an object")
    schedule_id = _payload_uuid(payload, "refresh_schedule_id")
    source_import_id = _payload_uuid(payload, "source_import_id")

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                select ci.id, ci.tenant_id, ci.supplier_id, ci.file_path, ci.file_name,
                       ci.file_format, ors.id as schedule_id
                from catalogue_imports ci
                join offer_refresh_schedule ors
                  on ors.tenant_id = ci.tenant_id
                 and ors.source_import_id = ci.id
                where ci.id = %s and ci.tenant_id = %s and ors.id = %s
                  and ci.status = 'completed'
                """,
                (source_import_id, job["tenant_id"], schedule_id),
            )
            source = cur.fetchone()
            if source is None:
                raise ValueError("refresh source is unavailable")

        if source["file_format"] != "csv":
            raise ValueError("scheduled refresh currently supports CSV sources only")
        content = _download(settings, str(source["file_path"]))
        connector = CsvCatalogueConnector(
            content,
            filename=str(source["file_name"]),
            observed_at=datetime.now(UTC),
            default_base_unit="each",
        )
        page = connector.list_catalogue()
        normalized_rows = [
            {
                "provider_record_id": row.provider_record_id,
                "product_name": row.product_name,
                "unit_price_amount": str(row.unit_price_amount),
                "unit_price_currency": row.unit_price_currency,
                "base_unit": row.base_unit,
                "observed_at": row.observed_at.isoformat(),
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                "supplier_sku": row.supplier_sku,
            }
            for row in page.rows
        ]
        errors = list(page.errors)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into catalogue_refresh_review
                  (tenant_id, refresh_schedule_id, source_import_id, supplier_id,
                   normalized_rows, errors, row_count, error_count)
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (tenant_id, refresh_schedule_id, source_import_id)
                do update set normalized_rows = excluded.normalized_rows,
                              errors = excluded.errors,
                              row_count = excluded.row_count,
                              error_count = excluded.error_count
                returning id
                """,
                (
                    source["tenant_id"],
                    schedule_id,
                    source_import_id,
                    source["supplier_id"],
                    Jsonb(normalized_rows),
                    Jsonb(errors),
                    len(normalized_rows),
                    len(errors),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("refresh review was not created")
    return UUID(str(row["id"]))


def _download(settings: Settings, path: str) -> bytes:
    client = create_client(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
    return bytes(client.storage.from_(settings.quotation_documents_bucket).download(path))


def _mark_completed(settings: Settings, job_id: UUID, review_id: UUID) -> None:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                update ingestion_jobs
                set status = 'completed', completed_at = now(), locked_by = null,
                    locked_at = null, last_error = null,
                    payload = payload || %s, updated_at = now()
                where id = %s
                """,
                (Jsonb({"refresh_review_id": str(review_id)}), job_id),
            )
        conn.commit()


def _mark_failed(
    settings: Settings,
    job_id: UUID,
    *,
    attempts: int,
    max_attempts: int,
    error: str,
) -> None:
    next_status = "failed" if attempts + 1 >= max_attempts else "pending"
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                update ingestion_jobs
                set status = %s::ingestion_job_status, attempts = attempts + 1,
                    last_error = %s, locked_by = null, locked_at = null,
                    completed_at = case when %s = 'failed' then now() else null end,
                    updated_at = now()
                where id = %s
                """,
                (next_status, error[:1000], next_status, job_id),
            )
        conn.commit()


def _payload_uuid(payload: dict[str, object], name: str) -> UUID:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ValueError(f"catalogue refresh payload missing {name}")
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"catalogue refresh payload has invalid {name}") from exc


def run_loop(settings: Settings, *, once: bool = False, interval_seconds: int = 30) -> None:
    logger.info("Starting catalogue refresh worker (once=%s, interval=%ss)", once, interval_seconds)
    while True:
        try:
            stats = tick(settings)
            if stats["claimed"]:
                logger.info("Catalogue refresh pass completed: %s", stats)
        except Exception:
            logger.exception("Error during catalogue refresh worker pass")
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalogue refresh review worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=30)
    args = parser.parse_args()
    run_loop(get_settings(), once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
