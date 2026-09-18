from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.ingestion.schemas import (
    IngestionEmailLog,
    IngestionEmailLogList,
    IngestionEmailStatus,
)
from procurepilot_api.modules.offers.service import _authenticated_db


class IngestionEmailLogService:
    """T019: Ingestion email log listing service. Cursor-paginated listing of inbound email
    logs for the caller's tenant, newest first."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_email_logs(
        self,
        *,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = 50,
        status: IngestionEmailStatus | None = None,
        from_domain: str | None = None,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
    ) -> IngestionEmailLogList:
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100)

        parsed_date_from = _parse_date_bound(date_from, is_end=False)
        parsed_date_to = _parse_date_bound(date_to, is_end=True)

        clauses = ["tenant_id = %(tenant_id)s"]
        params: dict[str, Any] = {
            "tenant_id": member.tenant_id,
            "offset": offset,
            "limit": fetch_limit + 1,
        }

        if status is not None:
            clauses.append("status = %(status)s")
            params["status"] = status
        if from_domain is not None:
            clauses.append("from_domain = %(from_domain)s")
            params["from_domain"] = from_domain
        if parsed_date_from is not None:
            clauses.append("received_at >= %(date_from)s")
            params["date_from"] = parsed_date_from
        if parsed_date_to is not None:
            clauses.append("received_at <= %(date_to)s")
            params["date_to"] = parsed_date_to

        where_sql = " where " + " and ".join(clauses)

        query = f"""
            select
                id,
                message_id,
                from_address,
                from_domain,
                subject,
                received_at,
                processed_at,
                status,
                error_message,
                attachment_count,
                quotation_id,
                supplier_id,
                match_method,
                created_at
            from ingestion_email_log
            {where_sql}
            order by received_at desc, id desc
            offset %(offset)s limit %(limit)s
        """

        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                rows = [dict(r) for r in cur.fetchall()]

        has_more = len(rows) > fetch_limit
        page_rows = rows[:fetch_limit]
        next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None

        return IngestionEmailLogList(
            items=[_map_log_entry(r) for r in page_rows],
            next_cursor=next_cursor,
        )


def get_ingestion_email_log_service() -> IngestionEmailLogService:
    return IngestionEmailLogService()


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if offset < 0:
            raise UnprocessableEntityError(details={"cursor": "invalid"})
        return offset
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc


def _parse_date_bound(val: datetime | str | None, *, is_end: bool = False) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        try:
            if len(cleaned) == 10:
                dt = datetime.fromisoformat(cleaned)
                if is_end:
                    return dt.replace(
                        hour=23, minute=59, second=59, microsecond=999999, tzinfo=UTC
                    )
                return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
            dt = datetime.fromisoformat(cleaned)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError) as exc:
            field = "date_to" if is_end else "date_from"
            raise UnprocessableEntityError(details={field: "invalid_format"}) from exc
    raise UnprocessableEntityError(details={"date": "invalid_type"})


def _map_log_entry(row: dict[str, Any]) -> IngestionEmailLog:
    return IngestionEmailLog(
        id=row["id"],
        message_id=str(row["message_id"]),
        from_address=str(row["from_address"]),
        from_domain=str(row["from_domain"]),
        subject=str(row["subject"]) if row.get("subject") is not None else None,
        received_at=row["received_at"],
        processed_at=row.get("processed_at"),
        status=row["status"],
        error_message=str(row["error_message"]) if row.get("error_message") is not None else None,
        attachment_count=int(row["attachment_count"]),
        quotation_id=row.get("quotation_id"),
        supplier_id=row.get("supplier_id"),
        match_method=row.get("match_method"),
        created_at=row["created_at"],
    )
