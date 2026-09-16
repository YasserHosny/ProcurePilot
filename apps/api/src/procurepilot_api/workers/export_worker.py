from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.exports.renderers import render_csv, render_pdf, render_xlsx
from procurepilot_api.modules.exports.storage import ExportStorage
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

logger = logging.getLogger(__name__)


def process_export_job(payload: dict[str, str]) -> dict[str, Any]:
    """Process an export job, treating the queue payload as an untrusted hint (FR-007)."""
    job_id = UUID(payload["job_id"])
    provided_tenant_id = UUID(payload["tenant_id"]) if "tenant_id" in payload else None
    settings = get_settings()

    # Step 1: Re-derive tenant_id and verify queue payload
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select * from export_job where id = %s", (job_id,))
            initial_row = cur.fetchone()

    if initial_row is None:
        logger.error("Export job %s not found", job_id)
        raise RuntimeError("export_job_not_found")

    real_tenant_id = UUID(str(initial_row["tenant_id"]))
    if provided_tenant_id is not None and provided_tenant_id != real_tenant_id:
        logger.error(
            "Untrusted queue payload mismatch: provided tenant %s != real tenant %s for job %s",
            provided_tenant_id,
            real_tenant_id,
            job_id,
        )
        raise RuntimeError("tenant_payload_mismatch")

    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            _act_as_tenant(conn, real_tenant_id)
            row = _mark_running(conn, job_id)
            conn.commit()

            # Record run_started audit event
            _record_worker_audit(
                tenant_id=real_tenant_id,
                actor_id=UUID(str(row["requested_by"])),
                action="reports.run_started",
                target={
                    "export_job_id": str(job_id),
                    "kind": str(row["kind"]),
                    "format": str(row["format"]),
                    "schedule_id": str(row["schedule_id"]) if row.get("schedule_id") else None,
                },
            )

            # Step 2: Extract filters and fetch report rows using authorization-pinned readers
            filters = _json_object(row["filters"])
            kind = str(row["kind"])
            rows = _fetch_report_rows(conn, tenant_id=real_tenant_id, kind=kind, filters=filters)

            # Step 3: Render content
            fmt = str(row["format"])
            locale = str(row.get("locale") or "en")
            if fmt == "csv":
                content = render_csv(rows, kind=kind, locale=locale)
            elif fmt == "xlsx":
                content = render_xlsx(rows, kind=kind, locale=locale)
            else:
                content = render_pdf(rows, kind=kind, locale=locale)

            # Step 4: Upload to storage
            bucket, path, download_url = ExportStorage(settings).upload(
                tenant_id=real_tenant_id,
                job_id=job_id,
                format=fmt,
                content=content,
            )

            # Step 5: Mark completed with retention expires_at
            expires_at = datetime.now(UTC) + timedelta(days=settings.export_retention_days)
            _mark_completed(
                conn,
                job_id=job_id,
                bucket=bucket,
                path=path,
                download_url=download_url,
                row_count=len(rows),
                expires_at=expires_at,
            )
            conn.commit()

            # Record run_completed audit event
            _record_worker_audit(
                tenant_id=real_tenant_id,
                actor_id=UUID(str(row["requested_by"])),
                action="reports.run_completed",
                target={
                    "export_job_id": str(job_id),
                    "kind": kind,
                    "format": fmt,
                    "row_count": len(rows),
                    "schedule_id": str(row["schedule_id"]) if row.get("schedule_id") else None,
                },
            )

            return {"job_id": str(job_id), "status": "completed", "row_count": len(rows)}

    except Exception as exc:
        _persist_failure(settings, tenant_id=real_tenant_id, job_id=job_id, exc=exc)
        if initial_row:
            _record_worker_audit(
                tenant_id=real_tenant_id,
                actor_id=UUID(str(initial_row["requested_by"])),
                action="reports.run_failed",
                target={
                    "export_job_id": str(job_id),
                    "kind": str(initial_row["kind"]),
                    "format": str(initial_row["format"]),
                    "error": exc.__class__.__name__,
                },
                outcome="failure",
            )
        raise


def main() -> None:
    from redis import Redis
    from rq import Worker

    settings = get_settings()
    worker = Worker([settings.export_queue_name], connection=Redis.from_url(settings.redis_url))
    worker.work()


def _fetch_report_rows(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    kind: str,
    filters: dict[str, object],
) -> list[dict[str, object]]:
    """Fetch report records via the authorization-pinned reader functions (FR-007)."""
    period_start = filters.get("period_start")
    period_end = filters.get("period_end")
    supplier_id = filters.get("supplier_id")
    branch_id = filters.get("branch_id")

    if kind == "spend_by_supplier":
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from reporting_purchases_for_period(
                    %(tenant_id)s, %(period_start)s, %(period_end)s, %(supplier_id)s, %(branch_id)s
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "supplier_id": supplier_id,
                    "branch_id": branch_id,
                },
            )
            purchases = [dict(r) for r in cur.fetchall()]

        # Group by (supplier, currency) — never sum across currencies per data-model.md
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        branch_counts: dict[tuple[str, str], dict[str, int]] = {}
        for p in purchases:
            supp_key = str(p.get("supplier_id") or p.get("supplier_name") or "unknown")
            curr_key = str(p.get("total_paid_currency") or "")
            key = (supp_key, curr_key)
            if key not in grouped:
                grouped[key] = {
                    "supplier_name": p.get("supplier_name") or "—",
                    "tax_number": "—",
                    "currency": curr_key,
                    "total_spend": 0.0,
                    "order_count": 0,
                    "realised_savings": 0.0,
                    "primary_branch": "—",
                }
                branch_counts[key] = {}
            item = grouped[key]
            item["total_spend"] += float(p.get("total_paid_amount") or 0)
            item["order_count"] += 1
            if p.get("saving_status") == "verified":
                item["realised_savings"] += float(p.get("saving_delta_amount") or 0)
            br = p.get("attributed_branch_name")
            if br:
                branch_counts[key][br] = branch_counts[key].get(br, 0) + 1

        for key, item in grouped.items():
            item["total_spend"] = f"{item['total_spend']:.2f}"
            item["realised_savings"] = f"{item['realised_savings']:.2f}"
            counts = branch_counts[key]
            if counts:
                item["primary_branch"] = max(counts.items(), key=lambda x: x[1])[0]

        return list(grouped.values())

    if kind == "alerts_summary":
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from reporting_alert_snapshot(
                    %(tenant_id)s, %(period_start)s, %(period_end)s, %(branch_id)s
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "branch_id": branch_id,
                },
            )
            snapshots = [dict(r) for r in cur.fetchall()]

        alerts_list: list[dict[str, object]] = []
        for s in snapshots:
            alerts_list.append(
                {
                    "id": str(s.get("landed_cost_id") or ""),
                    "triggered_at": s.get("recorded_at"),
                    "alert_type": "offer_alert",
                    "severity": "medium",
                    "supplier_name": s.get("supplier_name") or "—",
                    "product_name": s.get("product_name") or s.get("canonical_name") or "—",
                    "branch_name": "—",
                    "exposure_amount": s.get("total_amount") or 0,
                    "currency": s.get("total_currency") or "",
                    "status": "active",
                    "dismissed_by": "—",
                    "dismissal_reason": "—",
                }
            )
        return alerts_list

    # Default: savings_ledger
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select * from reporting_savings_for_period(
                %(tenant_id)s, %(period_start)s, %(period_end)s, %(supplier_id)s, %(branch_id)s
            )
            """,
            {
                "tenant_id": tenant_id,
                "period_start": period_start,
                "period_end": period_end,
                "supplier_id": supplier_id,
                "branch_id": branch_id,
            },
        )
        return [dict(r) for r in cur.fetchall()]


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
    expires_at: datetime,
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
                expires_at = %s,
                error = null
            where id = %s
            """,
            (bucket, path, download_url, row_count, datetime.now(UTC), expires_at, job_id),
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


def _record_worker_audit(
    *,
    tenant_id: UUID,
    actor_id: UUID,
    action: str,
    target: dict[str, object],
    outcome: str = "success",
) -> None:
    try:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=tenant_id,
                actor_membership_id=actor_id,
                actor_email="worker@procurepilot.local",
                action=action,
                target=target,
                outcome=outcome,
                trace_id=get_trace_id(),
            )
        )
    except Exception as exc:
        logger.warning("Failed to record worker audit event %s: %s", action, exc)


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
