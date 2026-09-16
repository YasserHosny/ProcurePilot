from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ExportRowCapExceededError,
    NotFoundError,
    ServiceUnavailableError,
)
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters, ExportJob
from procurepilot_api.modules.exports.storage import ExportStorage
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.reports.schedules import authorize_filters, workspace_context
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id


class ExportService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_job(
        self,
        *,
        member: CurrentMember,
        payload: ExportCreate,
        bearer_token: str | None = None,
    ) -> ExportJob:
        with _authenticated_db(self._settings, member) as conn:
            workspace = workspace_context(conn, member)
            filters = _resolved_filters(payload.filters, workspace)
            authorize_filters(
                conn,
                member=member,
                supplier_id=payload.filters.supplier_id,
                branch_id=payload.filters.branch_id,
            )
            _enforce_row_cap(
                conn,
                member=member,
                kind=payload.kind,
                filters=filters,
                cap=self._settings.export_row_cap,
            )
            locale = payload.locale or str(
                workspace["preferred_locale"] or workspace["default_locale"]
            )
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into export_job
                      (tenant_id, requested_by, kind, format, filters, status, locale)
                    values (%s, %s, %s, %s, %s, 'queued', %s)
                    returning *
                    """,
                    (
                        member.tenant_id,
                        member.membership_id,
                        payload.kind,
                        payload.format,
                        Jsonb(filters.model_dump(mode="json")),
                        locale,
                    ),
                )
                row = dict(cur.fetchone())
            try:
                _enqueue_export_job(self._settings, row, member)
            except ServiceUnavailableError:
                _mark_enqueue_failed(conn, UUID(str(row["id"])))
                conn.commit()
                raise
            conn.commit()
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="reports.export_requested",
            target={
                "export_job_id": str(row["id"]),
                "kind": payload.kind,
                "format": payload.format,
                "period_start": filters.period_start.isoformat(),
                "period_end": filters.period_end.isoformat(),
            },
        )
        return _job(row)

    def get_job(self, *, member: CurrentMember, job_id: UUID) -> ExportJob:
        with _authenticated_db(self._settings, member) as conn:
            row = _job_row(conn, job_id)
        return _job(row)

    def create_download_url(
        self,
        *,
        member: CurrentMember,
        job_id: UUID,
        bearer_token: str,
    ) -> str:
        with _authenticated_db(self._settings, member) as conn:
            row = _job_row(conn, job_id)
            _enforce_download_visibility(conn, member, row)
        url = ExportStorage(self._settings).create_signed_url(
            bucket=str(row["storage_bucket"]),
            path=str(row["storage_path"]),
            ttl_seconds=self._settings.export_download_url_ttl_seconds,
        )
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="reports.artifact_downloaded",
            target={
                "export_job_id": str(row["id"]),
                "kind": str(row["kind"]),
                "format": str(row["format"]),
                "row_count": row.get("row_count"),
            },
        )
        return url


def _enforce_download_visibility(
    conn: object,
    member: CurrentMember,
    row: dict[str, object],
) -> None:
    """FR-005: authenticated job lookup verifies caller branch visibility against the
    artifact's branch filter, returning not found when unauthorised, purged, or expired."""
    if (
        row.get("status") != "completed"
        or row.get("storage_bucket") is None
        or row.get("storage_path") is None
    ):
        raise NotFoundError(details={"resource": "export_download"})

    expires_at = row.get("expires_at")
    if expires_at is not None:
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except ValueError:
                pass
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise NotFoundError(details={"resource": "export_download"})

    if member.role.value == "owner":
        return

    raw_filters = row.get("filters")
    filters_dict: dict[str, object] = {}
    if isinstance(raw_filters, str):
        try:
            filters_dict = json.loads(raw_filters)
        except Exception:
            filters_dict = {}
    elif isinstance(raw_filters, dict):
        filters_dict = raw_filters

    branch_id = filters_dict.get("branch_id")
    if not branch_id:
        return

    with conn.cursor() as cur:
        cur.execute(
            "select branch_id from branch_role_assignment"
            " where membership_id = %s and tenant_id = %s",
            (member.membership_id, member.tenant_id),
        )
        assigned = {str(r[0]) for r in cur.fetchall()}

    if assigned and str(branch_id) not in assigned:
        raise NotFoundError(details={"resource": "export_download"})


def _resolved_filters(filters: ExportFilters, workspace: dict[str, object]) -> ExportFilters:
    """An omitted period_end means "through today" in the workspace's reporting timezone
    (FR-012) — resolved at submission so the stored snapshot is concrete."""
    if filters.period_end is not None:
        return filters
    today = datetime.now(UTC).astimezone(ZoneInfo(str(workspace["reporting_timezone"]))).date()
    return ExportFilters(
        period_start=filters.period_start,
        period_end=today,
        supplier_id=filters.supplier_id,
        branch_id=filters.branch_id,
    )


def _enforce_row_cap(
    conn: object,
    *,
    member: CurrentMember,
    kind: str,
    filters: ExportFilters,
    cap: int,
) -> None:
    """FR-013: count the rows the artifact would carry via the landed readers and refuse
    over-cap requests at submission — nothing is queued."""
    if kind == "alerts_summary":
        reader = (
            "reporting_alert_snapshot("
            "%(tenant_id)s, %(period_start)s, %(period_end)s, %(branch_id)s)"
        )
    elif kind == "spend_by_supplier":
        reader = (
            "reporting_purchases_for_period("
            "%(tenant_id)s, %(period_start)s, %(period_end)s, %(supplier_id)s, %(branch_id)s)"
        )
    else:
        reader = (
            "reporting_savings_for_period("
            "%(tenant_id)s, %(period_start)s, %(period_end)s, %(supplier_id)s, %(branch_id)s)"
        )
    with conn.cursor() as cur:
        cur.execute(
            f"select count(*) from {reader}",
            {
                "tenant_id": member.tenant_id,
                "period_start": filters.period_start,
                "period_end": filters.period_end,
                "supplier_id": filters.supplier_id,
                "branch_id": filters.branch_id,
            },
        )
        actual = int(cur.fetchone()[0])
    if actual > cap:
        raise ExportRowCapExceededError(details={"cap": cap, "actual": actual})


def get_export_service() -> ExportService:
    return ExportService()


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=member.tenant_id,
            actor_membership_id=member.membership_id,
            actor_email=member.email,
            action=action,
            target=target,
            outcome="success",
            trace_id=get_trace_id(),
        ),
        bearer_token=bearer_token,
    )


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
        locale=str(row["locale"]) if row.get("locale") else None,
        row_count=row.get("row_count"),
        download_url=row.get("download_url"),
        error=row.get("error"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )
