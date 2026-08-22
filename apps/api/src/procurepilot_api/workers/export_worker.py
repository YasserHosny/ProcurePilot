from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.exports.renderers import render_pdf, render_xlsx
from procurepilot_api.modules.exports.service import verified_savings_for_export
from procurepilot_api.modules.exports.storage import ExportStorage

logger = logging.getLogger(__name__)


def process_export_job(payload: dict[str, str]) -> dict[str, Any]:
    job_id = UUID(payload["job_id"])
    tenant_id = UUID(payload["tenant_id"])
    settings = get_settings()
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            _act_as_tenant(conn, tenant_id)
            row = _mark_running(conn, job_id)
            conn.commit()
            filters = _json_object(row["filters"])
            rows = verified_savings_for_export(conn, filters=filters)
            content = render_xlsx(rows) if row["format"] == "xlsx" else render_pdf(rows)
            bucket, path, download_url = ExportStorage(settings).upload(
                tenant_id=tenant_id,
                job_id=job_id,
                format=str(row["format"]),
                content=content,
            )
            _mark_completed(
                conn,
                job_id=job_id,
                bucket=bucket,
                path=path,
                download_url=download_url,
                row_count=len(rows),
            )
            conn.commit()
            return {"job_id": str(job_id), "status": "completed", "row_count": len(rows)}
    except Exception as exc:
        _persist_failure(settings, tenant_id=tenant_id, job_id=job_id, exc=exc)
        raise


def main() -> None:
    from redis import Redis
    from rq import Worker

    settings = get_settings()
    worker = Worker([settings.export_queue_name], connection=Redis.from_url(settings.redis_url))
    worker.work()


def _act_as_tenant(conn: psycopg.Connection, tenant_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"tenant_id": str(tenant_id), "role": "authenticated"}),),
        )


def _mark_running(conn: psycopg.Connection, job_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update export_job
            set status = 'running', started_at = coalesce(started_at, now()), error = null
            where id = %s and status in ('queued', 'running')
            returning *
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("export_job_not_runnable")
    return dict(row)


def _mark_completed(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    bucket: str,
    path: str,
    download_url: str,
    row_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update export_job
            set status = 'completed',
                storage_bucket = %s,
                storage_path = %s,
                download_url = %s,
                row_count = %s,
                completed_at = %s,
                error = null
            where id = %s
            """,
            (bucket, path, download_url, row_count, datetime.now(UTC), job_id),
        )


def _persist_failure(settings: Settings, *, tenant_id: UUID, job_id: UUID, exc: Exception) -> None:
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _act_as_tenant(conn, tenant_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                update export_job
                set status = 'failed',
                    error = %s,
                    completed_at = coalesce(completed_at, %s)
                where id = %s and status <> 'completed'
                """,
                (
                    Jsonb(
                        {
                            "code": "export_render_failed",
                            "message": "Export job failed.",
                            "details": {"exception": exc.__class__.__name__},
                        }
                    ),
                    datetime.now(UTC),
                    job_id,
                ),
            )
        conn.commit()


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    raise RuntimeError("invalid_export_filters")


if __name__ == "__main__":
    main()
