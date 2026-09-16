from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg.errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ScheduleCapExceededError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.reports.schemas import (
    ReportArtifact,
    ReportArtifactList,
    ReportFilters,
    ReportSchedule,
    ReportScheduleList,
    ReportScheduleUpdate,
    validate_kind_format_matrix,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id


def derive_weekly_window(run_at: datetime, timezone_name: str) -> tuple[date, date]:
    """The prior COMPLETE week in the workspace's reporting timezone (FR-003).

    The window is derived from the local date, never the UTC date: a Monday-morning run in
    Karachi (UTC+5) still belongs to the week ending the previous Sunday, local time.
    """
    local_date = run_at.astimezone(ZoneInfo(timezone_name)).date()
    return local_date - timedelta(days=7), local_date - timedelta(days=1)


def next_run_after(weekday: int, after: datetime, timezone_name: str) -> datetime:
    """The next local midnight on `weekday` strictly after `after`, as UTC (0 = Monday)."""
    if not 0 <= weekday <= 6:
        raise ValueError("weekday must be between 0 and 6")
    tz = ZoneInfo(timezone_name)
    local_after = after.astimezone(tz)
    for day_offset in range(15):
        candidate_date = local_after.date() + timedelta(days=day_offset)
        if candidate_date.weekday() != weekday:
            continue
        midnight = datetime.combine(candidate_date, time(), tz)
        if midnight.astimezone(UTC) > after:
            return midnight.astimezone(UTC)
    raise ValueError("no matching weekday within two weeks")


def period_idempotency_key(schedule_id: UUID, period_start: date) -> str:
    """Deterministic queue-safe job id for one schedule's one period (doubles as the RQ id)."""
    return f"{schedule_id}:{period_start.isoformat()}"


def canonical_filters_digest(filters: dict[str, object]) -> str:
    """The sha256 of the canonical filters JSON — byte-identical to seed.py's helper."""
    canonical = json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReportsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_schedule(
        self,
        *,
        member: CurrentMember,
        kind: str,
        format: str,
        filters: ReportFilters,
        weekday: int,
        locale: str | None,
        bearer_token: str | None = None,
    ) -> ReportSchedule:
        validate_kind_format_matrix(kind, format)
        filter_values = filters.model_dump(mode="json")
        digest = canonical_filters_digest(filter_values)
        with _authenticated_db(self._settings, member) as conn:
            workspace = workspace_context(conn, member)
            authorize_filters(
                conn,
                member=member,
                supplier_id=filters.supplier_id,
                branch_id=filters.branch_id,
            )
            _enforce_schedule_cap(
                conn,
                member=member,
                cap=self._settings.active_schedule_cap_per_member,
            )
            resolved_locale = locale or workspace["preferred_locale"] or workspace["default_locale"]
            next_run = next_run_after(
                weekday, datetime.now(UTC), str(workspace["reporting_timezone"])
            )
            try:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        insert into report_schedule
                          (tenant_id, created_by_membership_id, kind, format, filters,
                           filters_digest, weekday, status, next_run_at, rule_version, locale)
                        values (%s, %s, %s, %s, %s, %s, %s, 'active', %s, '', %s)
                        returning *
                        """,
                        (
                            member.tenant_id,
                            member.membership_id,
                            kind,
                            format,
                            Jsonb(filter_values),
                            digest,
                            weekday,
                            next_run,
                            resolved_locale,
                        ),
                    )
                    row = dict(cur.fetchone())
            except psycopg.errors.UniqueViolation as exc:
                raise ConflictError(
                    details={"reason": "schedule_already_exists", "filters_digest": digest}
                ) from exc
            conn.commit()
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="reports.schedule_created",
            target={"report_schedule_id": str(row["id"]), "kind": kind, "format": format},
        )
        return _schedule(row)

    def list_schedules(
        self,
        *,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReportScheduleList:
        capped = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select * from report_schedule
                    order by created_at desc, id desc
                    limit %(limit)s offset %(offset)s
                    """,
                    {"limit": capped + 1, "offset": offset},
                )
                rows = [dict(row) for row in cur.fetchall()]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None
        return ReportScheduleList(
            items=[_schedule(row) for row in rows[:capped]], next_cursor=next_cursor
        )

    def get_schedule(self, *, member: CurrentMember, schedule_id: UUID) -> ReportSchedule:
        with _authenticated_db(self._settings, member) as conn:
            row = _schedule_row(conn, schedule_id)
        return _schedule(row)

    def update_schedule(
        self,
        *,
        member: CurrentMember,
        schedule_id: UUID,
        payload: ReportScheduleUpdate,
        bearer_token: str | None = None,
    ) -> ReportSchedule:
        with _authenticated_db(self._settings, member) as conn:
            existing = _schedule_row(conn, schedule_id)
            status_changed = payload.status is not None and payload.status != existing["status"]
            field_changed = any(
                (
                    payload.format is not None,
                    payload.filters is not None,
                    payload.weekday is not None,
                    payload.locale is not None,
                )
            )
            if payload.format is not None:
                validate_kind_format_matrix(str(existing["kind"]), payload.format)
            filters = (
                payload.filters
                if payload.filters is not None
                else ReportFilters.model_validate(existing["filters"])
            )
            if payload.filters is not None:
                authorize_filters(
                    conn,
                    member=member,
                    supplier_id=filters.supplier_id,
                    branch_id=filters.branch_id,
                )
            weekday = payload.weekday if payload.weekday is not None else int(existing["weekday"])
            locale = payload.locale if payload.locale is not None else str(existing["locale"])
            workspace = workspace_context(conn, member)
            recompute_next_run = payload.weekday is not None or (
                status_changed and payload.status == "active"
            )
            next_run = (
                next_run_after(weekday, datetime.now(UTC), str(workspace["reporting_timezone"]))
                if recompute_next_run
                else existing["next_run_at"]
            )
            filter_values = filters.model_dump(mode="json")
            digest = canonical_filters_digest(filter_values)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    update report_schedule
                    set format = %s, filters = %s, filters_digest = %s, weekday = %s,
                        locale = %s, status = %s, next_run_at = %s, updated_at = now()
                    where id = %s
                    returning *
                    """,
                    (
                        payload.format or existing["format"],
                        Jsonb(filter_values),
                        digest,
                        weekday,
                        locale,
                        payload.status or existing["status"],
                        next_run,
                        schedule_id,
                    ),
                )
                row = dict(cur.fetchone())
            conn.commit()
        if status_changed:
            _record_audit(
                bearer_token=bearer_token,
                member=member,
                action=(
                    "reports.schedule_paused"
                    if payload.status == "paused"
                    else "reports.schedule_resumed"
                ),
                target={"report_schedule_id": str(schedule_id)},
            )
        if field_changed:
            _record_audit(
                bearer_token=bearer_token,
                member=member,
                action="reports.schedule_updated",
                target={"report_schedule_id": str(schedule_id)},
            )
        return _schedule(row)

    def delete_schedule(
        self,
        *,
        member: CurrentMember,
        schedule_id: UUID,
        bearer_token: str | None = None,
    ) -> None:
        with _authenticated_db(self._settings, member) as conn:
            _schedule_row(conn, schedule_id)
            with conn.cursor() as cur:
                cur.execute("delete from report_schedule where id = %s", (schedule_id,))
            conn.commit()
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="reports.schedule_deleted",
            target={"report_schedule_id": str(schedule_id)},
        )

    def list_artifacts(
        self,
        *,
        member: CurrentMember,
        kind: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReportArtifactList:
        capped = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        clauses: list[str] = []
        params: dict[str, object] = {"limit": capped + 1, "offset": offset}
        if kind is not None:
            clauses.append("kind = %(kind)s")
            params["kind"] = kind
        if status is not None:
            clauses.append("status = %(status)s")
            params["status"] = status
        with _authenticated_db(self._settings, member) as conn:
            scope_clause, scope_params = _branch_scope_clause(conn, member)
            clauses.append(scope_clause)
            params.update(scope_params)
            where = "where " + " and ".join(clauses)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    select * from export_job {where}
                    order by created_at desc, id desc
                    limit %(limit)s offset %(offset)s
                    """,
                    params,
                )
                rows = [dict(row) for row in cur.fetchall()]
        next_cursor = _encode_cursor(offset + capped) if len(rows) > capped else None
        return ReportArtifactList(
            items=[_artifact(row) for row in rows[:capped]], next_cursor=next_cursor
        )


def get_reports_service() -> ReportsService:
    return ReportsService()


def _enforce_schedule_cap(conn: object, *, member: CurrentMember, cap: int) -> None:
    """T035 (FR-020): each active schedule is a standing recurring worker cost, so the count of
    a member's own active schedules is capped independently of how fast they were created."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*) from report_schedule
            where tenant_id = %(tenant_id)s
              and created_by_membership_id = %(membership_id)s
              and status = 'active'
            """,
            {"tenant_id": member.tenant_id, "membership_id": member.membership_id},
        )
        actual = int(cur.fetchone()[0])
    if actual >= cap:
        raise ScheduleCapExceededError(details={"cap": cap, "actual": actual})


def workspace_context(conn: object, member: CurrentMember) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select t.reporting_timezone, t.default_locale, m.preferred_locale
            from tenant t
            join membership m on m.tenant_id = t.id and m.id = %(membership_id)s
            where t.id = %(tenant_id)s
            """,
            {"tenant_id": member.tenant_id, "membership_id": member.membership_id},
        )
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "workspace"})
    return dict(row)


def authorize_filters(
    conn: object,
    *,
    member: CurrentMember,
    supplier_id: UUID | None,
    branch_id: UUID | None,
) -> None:
    """A named supplier or branch resolves as not found unless the caller can see it (FR-019).

    Two checks per reference, both required: the row must belong to the caller's tenant, and a
    branch-scoped member must hold an assignment for the branch. Cross-tenant and cross-branch
    references both resolve as not found — reporting never leaks existence.
    """
    if supplier_id is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                select exists (
                    select 1 from supplier s
                    where s.tenant_id = %(tenant_id)s and s.id = %(supplier_id)s
                )
                """,
                {"tenant_id": member.tenant_id, "supplier_id": supplier_id},
            )
            if not bool(cur.fetchone()[0]):
                raise NotFoundError(details={"resource": "supplier"})
    if branch_id is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            select exists (
                select 1 from branch b
                where b.tenant_id = %(tenant_id)s and b.id = %(branch_id)s and b.is_active
            )
            """,
            {"tenant_id": member.tenant_id, "branch_id": branch_id},
        )
        if not bool(cur.fetchone()[0]):
            raise NotFoundError(details={"resource": "branch"})
    if member.role.value == "owner":
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            select exists (
                select 1 from branch_role_assignment a
                where a.membership_id = %(membership_id)s
                  and a.branch_id = %(branch_id)s
            )
            """,
            {"membership_id": member.membership_id, "branch_id": branch_id},
        )
        has_assignment = bool(cur.fetchone()[0])
        if has_assignment:
            return
        cur.execute(
            """
            select not exists (
                select 1 from branch_role_assignment a
                where a.membership_id = %(membership_id)s
            )
            """,
            {"membership_id": member.membership_id},
        )
        if not bool(cur.fetchone()[0]):
            raise NotFoundError(details={"resource": "branch"})


def _branch_scope_clause(conn: object, member: CurrentMember) -> tuple[str, dict[str, object]]:
    """FR-004 listing scope: owners and unassigned members see every artifact; a member
    holding any branch assignment sees only artifacts filtered to their branches, plus
    the unfiltered ones."""
    if member.role.value == "owner":
        return "true", {}
    with conn.cursor() as cur:
        cur.execute(
            "select branch_id from branch_role_assignment where membership_id = %s",
            (member.membership_id,),
        )
        assigned = [row[0] for row in cur.fetchall()]
    if not assigned:
        return "true", {}
    placeholders = ", ".join(f"%(branch_{index})s" for index in range(len(assigned)))
    clause = f"(filters->>'branch_id' is null or filters->>'branch_id' in ({placeholders}))"
    params: dict[str, object] = {
        f"branch_{index}": str(value) for index, value in enumerate(assigned)
    }
    return clause, params


def _schedule_row(conn: object, schedule_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from report_schedule where id = %s", (schedule_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "report_schedule"})
    return dict(row)


def _schedule(row: dict[str, object]) -> ReportSchedule:
    filters = row["filters"]
    if isinstance(filters, str):
        filters = json.loads(filters)
    return ReportSchedule(
        id=UUID(str(row["id"])),
        kind=str(row["kind"]),
        format=str(row["format"]),
        filters=ReportFilters.model_validate(filters),
        weekday=int(row["weekday"]),
        status=str(row["status"]),
        next_run_at=row["next_run_at"],
        last_run_at=row.get("last_run_at"),
        rule_version=str(row.get("rule_version") or ""),
        locale=str(row["locale"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _artifact(row: dict[str, object]) -> ReportArtifact:
    filters = row["filters"]
    if isinstance(filters, str):
        filters = json.loads(filters)
    return ReportArtifact(
        id=UUID(str(row["id"])),
        kind=str(row["kind"]),
        format=str(row["format"]),
        filters=filters,
        status=str(row["status"]),
        row_count=row.get("row_count"),
        rule_version=str(row.get("rule_version") or ""),
        schedule_id=UUID(str(row["schedule_id"])) if row.get("schedule_id") else None,
        locale=str(row["locale"]),
        download_url=row.get("download_url"),
        expires_at=row.get("expires_at"),
        error=row.get("error"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )


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


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
