from __future__ import annotations

import base64
import json
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.ingestion.catalogue_parser import (
    CatalogueParseError,
    CatalogueRow,
    parse_catalogue_file,
)
from procurepilot_api.modules.ingestion.schemas import (
    CatalogueImportSummary,
    CatalogueImportSummaryList,
)
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, AuditOutcome, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

# T017 (research R6). Real finding that reshapes this task versus tasks.md's summary:
# MatchingService.quotation_matches() (the actual spec-004 matching entry point) refuses any
# quotation whose status is not already 'reviewed', and itself creates the landed_cost row for
# every line it auto-matches — there is no lighter "create an offer from a bare product+price"
# path anywhere in the codebase to call instead. So this orchestrator synthesizes one quotation
# (status='reviewed' from the moment it is created — the importing owner/buyer IS the human
# vouching for this bulk price list, the same role a reviewer plays for extracted data) with one
# quotation_line per catalogue row, then calls the existing, tested matching pipeline exactly as
# a real reviewed quotation would. See docs/operations/parallel-execution-plan-ingestion-wave3.md
# §2 for the full reasoning, including why this runs synchronously in the request rather than via
# ingestion_jobs (quotation_matches() authenticates with a real bearer token, which a background
# worker does not have).


def import_catalogue(
    settings: Settings,
    *,
    member: CurrentMember,
    supplier_id: UUID,
    file_content: bytes,
    filename: str,
    file_format: Literal["csv", "xlsx"],
    bearer_token: str,
) -> dict[str, object]:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from supplier where id = %s and tenant_id = %s",
                (supplier_id, member.tenant_id),
            )
            if cur.fetchone() is None:
                raise NotFoundError(details={"resource": "supplier"})

    _record_audit(
        bearer_token=bearer_token,
        member=member,
        action="catalogue_import_started",
        target={"supplier_id": str(supplier_id), "file_name": filename},
        outcome="success",
    )

    try:
        parsed = parse_catalogue_file(file_content, file_format=file_format)
    except CatalogueParseError as exc:
        import_id = _record_failed_import(
            settings,
            member=member,
            supplier_id=supplier_id,
            filename=filename,
            file_format=file_format,
            file_size_bytes=len(file_content),
            error=str(exc),
        )
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="catalogue_import_failed",
            target={"catalogue_import_id": str(import_id), "reason": str(exc)},
            outcome="refused",
        )
        raise UnprocessableEntityError(details={"reason": str(exc)}) from exc

    error_details: list[dict[str, object]] = [
        {"row": e.row_number, "column": e.column, "error": e.error} for e in parsed.error_rows
    ]

    with _authenticated_db(settings, member) as conn:
        document_id = _store_catalogue_document(settings, conn, member, filename, file_content)
        quotation_id = _insert_reviewed_quotation(conn, member, document_id, supplier_id)
        imported_rows = _insert_quotation_lines(
            conn, member, quotation_id, parsed.valid_rows, error_details
        )
        conn.commit()

    if imported_rows:
        MatchingService(settings).quotation_matches(
            bearer_token=bearer_token, member=member, quotation_id=quotation_id
        )

    status: Literal["completed", "failed"] = "completed" if imported_rows else "failed"
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into catalogue_imports
                  (tenant_id, supplier_id, file_name, file_path, file_size_bytes, file_format,
                   status, total_rows, imported_rows, skipped_rows, error_rows, error_details,
                   column_mapping, completed_at, created_by)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, now(), %s)
                returning *
                """,
                (
                    member.tenant_id,
                    supplier_id,
                    filename,
                    f"tenants/{member.tenant_id}/quotations/{document_id}/{filename}",
                    len(file_content),
                    file_format,
                    status,
                    parsed.total_rows,
                    imported_rows,
                    len(error_details),
                    Jsonb(error_details),
                    Jsonb(parsed.column_mapping),
                    member.membership_id,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()

    _record_audit(
        bearer_token=bearer_token,
        member=member,
        action="catalogue_import_completed" if status == "completed" else "catalogue_import_failed",
        target={
            "catalogue_import_id": str(row["id"]),
            "quotation_id": str(quotation_id),
            "imported_rows": imported_rows,
            "error_rows": len(error_details),
        },
        outcome="success" if status == "completed" else "refused",
    )
    return row


def list_imports(
    *,
    member: CurrentMember,
    supplier_id: UUID,
    cursor: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> CatalogueImportSummaryList:
    offset = _decode_cursor(cursor)
    fetch_limit = min(max(limit, 1), 100)
    active_settings = settings or get_settings()

    with _authenticated_db(active_settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from supplier where id = %s and tenant_id = %s",
                (supplier_id, member.tenant_id),
            )
            if cur.fetchone() is None:
                raise NotFoundError(details={"resource": "supplier"})

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select * from catalogue_imports
                where tenant_id = %(tenant_id)s and supplier_id = %(supplier_id)s
                order by created_at desc, id desc
                offset %(offset)s limit %(limit)s
                """,
                {
                    "tenant_id": member.tenant_id,
                    "supplier_id": supplier_id,
                    "offset": offset,
                    "limit": fetch_limit + 1,
                },
            )
            rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        if isinstance(r.get("error_details"), str):
            r["error_details"] = json.loads(r["error_details"])
        elif r.get("error_details") is None:
            r["error_details"] = []
        if isinstance(r.get("column_mapping"), str):
            r["column_mapping"] = json.loads(r["column_mapping"])
        elif r.get("column_mapping") is None:
            r["column_mapping"] = {}

    has_more = len(rows) > fetch_limit
    page_rows = rows[:fetch_limit]
    next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None
    return CatalogueImportSummaryList(
        items=[CatalogueImportSummary.model_validate(r) for r in page_rows],
        next_cursor=next_cursor,
    )


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        val = int(base64.urlsafe_b64decode(cursor.encode("ascii")))
        if val < 0:
            raise ValueError("negative cursor offset")
        return val
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc


def _store_catalogue_document(
    settings: Settings, conn: object, member: CurrentMember, filename: str, content: bytes
) -> UUID:
    document_id = uuid4()
    storage_path = f"tenants/{member.tenant_id}/quotations/{document_id}/{filename}"
    mime_type = (
        "text/csv"
        if filename.lower().endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    client = create_client(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
    client.storage.from_(settings.quotation_documents_bucket).upload(
        storage_path, content, {"content-type": mime_type, "upsert": "true"}
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into document
              (id, tenant_id, storage_bucket, storage_path, mime_type, source_channel, status,
               created_by)
            values (%s, %s, %s, %s, %s, 'catalogue_import', 'uploaded', %s)
            """,
            (
                document_id,
                member.tenant_id,
                settings.quotation_documents_bucket,
                storage_path,
                mime_type,
                member.membership_id,
            ),
        )
    return document_id


def _insert_reviewed_quotation(
    conn: object, member: CurrentMember, document_id: UUID, supplier_id: UUID
) -> UUID:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            insert into quotation
              (tenant_id, document_id, supplier_id, status, source, reviewed_by, reviewed_at)
            values (%s, %s, %s, 'reviewed', 'catalogue_import', %s, now())
            returning id
            """,
            (member.tenant_id, document_id, supplier_id, member.membership_id),
        )
        return UUID(str(cur.fetchone()["id"]))


def _insert_quotation_lines(
    conn: psycopg.Connection,
    member: CurrentMember,
    quotation_id: UUID,
    rows: list[CatalogueRow],
    error_details: list[dict[str, object]],
) -> int:
    imported = 0
    for line_number, row in enumerate(rows, start=1):
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into quotation_line
                          (tenant_id, quotation_id, line_number, original_text, quantity,
                           pack_unit, unit_price_amount, unit_price_currency)
                        values (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            member.tenant_id,
                            quotation_id,
                            line_number,
                            row.product_name,
                            row.minimum_order_quantity or 1,
                            None,
                            row.unit_price_amount,
                            row.unit_price_currency,
                        ),
                    )
            imported += 1
        except psycopg.errors.ForeignKeyViolation:
            error_details.append(
                {
                    "row": row.row_number,
                    "column": "currency",
                    "error": "unsupported_currency",
                }
            )
    return imported


def _record_failed_import(
    settings: Settings,
    *,
    member: CurrentMember,
    supplier_id: UUID,
    filename: str,
    file_format: str,
    file_size_bytes: int,
    error: str,
) -> UUID:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into catalogue_imports
                  (tenant_id, supplier_id, file_name, file_path, file_size_bytes, file_format,
                   status, error_details, completed_at, created_by)
                values (%s, %s, %s, '', %s, %s, 'failed', %s, now(), %s)
                returning id
                """,
                (
                    member.tenant_id,
                    supplier_id,
                    filename,
                    file_size_bytes,
                    file_format,
                    Jsonb([{"row": None, "column": None, "error": error}]),
                    member.membership_id,
                ),
            )
            import_id = UUID(str(cur.fetchone()["id"]))
        conn.commit()
    return import_id


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
    outcome: AuditOutcome,
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=member.tenant_id,
            actor_membership_id=member.membership_id,
            actor_email=member.email,
            action=action,
            target=target,
            outcome=outcome,
            trace_id=get_trace_id(),
        ),
        bearer_token=bearer_token,
    )
