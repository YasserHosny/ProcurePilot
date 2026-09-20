from __future__ import annotations

import base64
from collections.abc import Mapping
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.offers.schemas import (
    RefreshSchedule,
    RefreshScheduleCreate,
    RefreshScheduleList,
    RefreshScheduleUpdate,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

_SCHEDULE_COLUMNS = """
    id,
    workspace_product_id,
    supplier_id,
    cadence_days,
    status,
    next_refresh_at,
    last_observed_at,
    last_requested_at,
    last_error,
    source_import_id,
    created_at,
    updated_at
"""


def list_schedules(
    *,
    member: CurrentMember,
    cursor: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> RefreshScheduleList:
    offset = _decode_cursor(cursor)
    fetch_limit = min(max(limit, 1), 100)
    active_settings = settings or get_settings()
    with _authenticated_db(active_settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                select {_SCHEDULE_COLUMNS} from offer_refresh_schedule
                where tenant_id = %s
                order by created_at desc, id desc
                offset %s limit %s
                """,
                (member.tenant_id, offset, fetch_limit + 1),
            )
            rows = [dict(row) for row in cur.fetchall()]
    has_more = len(rows) > fetch_limit
    return RefreshScheduleList(
        items=[_schedule_from_row(row) for row in rows[:fetch_limit]],
        next_cursor=_encode_cursor(offset + fetch_limit) if has_more else None,
    )


def create_schedule(
    *,
    member: CurrentMember,
    payload: RefreshScheduleCreate,
    bearer_token: str | None = None,
    settings: Settings | None = None,
) -> RefreshSchedule:
    active_settings = settings or get_settings()
    with _authenticated_db(active_settings, member) as conn:
        _validate_product_and_supplier(
            conn, member, payload.workspace_product_id, payload.supplier_id
        )
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    insert into offer_refresh_schedule
                      (tenant_id, workspace_product_id, supplier_id, cadence_days)
                    values (%s, %s, %s, %s)
                    returning {_SCHEDULE_COLUMNS}
                    """,
                    (
                        member.tenant_id,
                        payload.workspace_product_id,
                        payload.supplier_id,
                        payload.cadence_days,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            conn.rollback()
            raise ConflictError(details={"reason": "refresh_schedule_exists"}) from exc
    if row is None:
        raise ConflictError(details={"reason": "refresh_schedule_not_created"})
    _record_audit(
        bearer_token=bearer_token,
        member=member,
        action="offers.refresh_schedule_created",
        target={"refresh_schedule_id": str(row["id"])},
    )
    return _schedule_from_row(row)


def update_schedule(
    *,
    member: CurrentMember,
    schedule_id: UUID,
    payload: RefreshScheduleUpdate,
    bearer_token: str | None = None,
    settings: Settings | None = None,
) -> RefreshSchedule:
    active_settings = settings or get_settings()
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise UnprocessableEntityError(details={"reason": "refresh_schedule_update_empty"})
    assignments = ", ".join(f"{key} = %s" for key in changes)
    values = [*changes.values(), member.tenant_id, schedule_id]
    with _authenticated_db(active_settings, member) as conn:
        if "source_import_id" in changes:
            _validate_source_import(
                conn,
                member,
                schedule_id,
                changes["source_import_id"],
            )
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                update offer_refresh_schedule
                set {assignments}, updated_at = now()
                where tenant_id = %s and id = %s
                returning {_SCHEDULE_COLUMNS}
                """,
                values,
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise NotFoundError(details={"resource": "refresh_schedule"})
    _record_audit(
        bearer_token=bearer_token,
        member=member,
        action="offers.refresh_schedule_updated",
        target={"refresh_schedule_id": str(schedule_id), "fields": list(changes)},
    )
    return _schedule_from_row(row)


def _schedule_from_row(row: Mapping[str, object]) -> RefreshSchedule:
    """Map the tenant-scoped database row to the public schedule contract."""
    return RefreshSchedule.model_validate(
        {
            "id": row["id"],
            "workspace_product_id": row["workspace_product_id"],
            "supplier_id": row["supplier_id"],
            "cadence_days": row["cadence_days"],
            "status": row["status"],
            "next_refresh_at": row["next_refresh_at"],
            "last_observed_at": row["last_observed_at"],
            "last_requested_at": row["last_requested_at"],
            "last_error": row["last_error"],
            "source_import_id": row["source_import_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def _record_audit(
    *, bearer_token: str | None, member: CurrentMember, action: str, target: dict[str, object]
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


def _validate_product_and_supplier(
    conn: psycopg.Connection,
    member: CurrentMember,
    product_id: UUID,
    supplier_id: UUID,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "select 1 from workspace_product where tenant_id = %s and id = %s",
            (member.tenant_id, product_id),
        )
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": "workspace_product"})
        cur.execute(
            "select 1 from supplier where tenant_id = %s and id = %s",
            (member.tenant_id, supplier_id),
        )
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": "supplier"})


def _validate_source_import(
    conn: psycopg.Connection,
    member: CurrentMember,
    schedule_id: UUID,
    source_import_id: UUID,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select s.supplier_id
            from offer_refresh_schedule s
            where s.tenant_id = %s and s.id = %s
            """,
            (member.tenant_id, schedule_id),
        )
        schedule = cur.fetchone()
        if schedule is None:
            raise NotFoundError(details={"resource": "refresh_schedule"})
        cur.execute(
            """
            select 1
            from catalogue_imports
            where tenant_id = %s
              and id = %s
              and supplier_id = %s
              and status = 'completed'
            """,
            (member.tenant_id, source_import_id, schedule[0]),
        )
        if cur.fetchone() is None:
            raise NotFoundError(details={"resource": "catalogue_import"})


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset
