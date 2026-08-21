from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportJob
from procurepilot_api.modules.offers.service import _authenticated_db


class ExportService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_job(self, *, member: CurrentMember, payload: ExportCreate) -> ExportJob:
        if payload.filters.branch_id is not None:
            raise UnprocessableEntityError(details={"branch_id": "unsupported_in_phase_1"})
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into export_job (tenant_id, requested_by, kind, format, filters, status)
                    values (%s, %s, %s, %s, %s, 'queued')
                    returning *
                    """,
                    (
                        member.tenant_id,
                        member.membership_id,
                        payload.kind,
                        payload.format,
                        Jsonb(payload.filters.model_dump(mode="json")),
                    ),
                )
                row = dict(cur.fetchone())
            try:
                _enqueue_export_job(self._settings, row, member)
            except ServiceUnavailableError:
                _mark_enqueue_failed(conn, UUID(str(row["id"])))
                conn.commit()
                raise
            return _job(row)

    def get_job(self, *, member: CurrentMember, job_id: UUID) -> ExportJob:
        with _authenticated_db(self._settings, member) as conn:
            row = _job_row(conn, job_id)
        return _job(row)


def get_export_service() -> ExportService:
    return ExportService()


def verified_savings_for_export(
    conn: object,
    *,
    filters: dict[str, object],
) -> list[dict[str, object]]:
    if filters.get("branch_id") is not None:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, purchase_record_id, workspace_product_id, supplier_id, recorded_at,
                   baseline_value_amount, baseline_value_currency, actual_value_amount,
                   actual_value_currency, delta_amount, delta_currency
            from saving_record
            where status = 'verified'
              and recorded_at::date >= %(period_start)s::date
              and recorded_at::date <= %(period_end)s::date
              and (%(supplier_id)s::uuid is null or supplier_id = %(supplier_id)s::uuid)
            order by recorded_at desc, id desc
            """,
            {
                "period_start": filters["period_start"],
                "period_end": filters["period_end"],
                "supplier_id": filters.get("supplier_id"),
            },
        )
        return [dict(row) for row in cur.fetchall()]


def _enqueue_export_job(settings: Settings, row: dict[str, object], member: CurrentMember) -> None:
    del member
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise ServiceUnavailableError(details={"dependency": "rq"}) from exc
    try:
        queue = Queue(settings.export_queue_name, connection=Redis.from_url(settings.redis_url))
        queue.enqueue(
            "procurepilot_api.workers.export_worker.process_export_job",
            {"job_id": str(row["id"]), "tenant_id": str(row["tenant_id"])},
            job_id=str(row["id"]),
        )
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "redis"}) from exc


def _mark_enqueue_failed(conn: object, job_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update export_job
            set status = 'failed',
                error = %s,
                completed_at = %s
            where id = %s
            """,
            (
                Jsonb(
                    {
                        "code": "redis_enqueue_failed",
                        "message": "Export job could not be queued in Redis.",
                    }
                ),
                datetime.now(UTC),
                job_id,
            ),
        )


def _job_row(conn: object, job_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from export_job where id = %s", (job_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "export_job"})
    return dict(row)


def _job(row: dict[str, object]) -> ExportJob:
    filters = row["filters"]
    if isinstance(filters, str):
        filters = json.loads(filters)
    return ExportJob(
        id=UUID(str(row["id"])),
        kind=str(row["kind"]),
        format=str(row["format"]),
        filters=filters,
        status=str(row["status"]),
        row_count=row.get("row_count"),
        download_url=row.get("download_url"),
        error=row.get("error"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )
