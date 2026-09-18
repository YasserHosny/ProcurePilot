from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from supabase import Client, create_client

from procurepilot_api.config import Settings
from procurepilot_api.modules.ingestion.email_parser import (
    EmailParseError,
    InboundEmail,
    ParsedAttachment,
    parse_email,
)
from procurepilot_api.modules.ingestion.extraction import enqueue_extraction as _enqueue_extraction
from procurepilot_api.modules.ingestion.matcher import match_supplier
from procurepilot_api.shared.audit import AuditEventCreate, AuditOutcome, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

logger = logging.getLogger(__name__)

# T011 (research R4, R2, spec.md acceptance scenarios 1-5): the email-ingestion orchestrator.
# Runs inside the worker (T012), never inline in the webhook request — the webhook (T014) only
# validates, rate-limits, and enqueues.
#
# Schema realities this orchestrator works within, found and documented during implementation
# rather than assumed from the spec docs:
# - `quotation.document_id` is a single required FK — there is no document<->quotation join
#   table, so one quotation can only ever have ONE primary document under the current schema,
#   and `extraction_job` enforces a unique active job per quotation.
#   spec.md acceptance scenario 2 ("each attachment produces a separate document record linked
#   to the same quotation") is only partly deliverable as a result: every attachment is uploaded
#   and stored as its own `document` row (for audit/replay, closing the data-loss gap), but only
#   the primary (first) attachment is wired to a quotation via `quotation.document_id` and queued
#   for extraction. This remains a real, deliberately-scoped product limitation — secondary
#   attachments are preserved in storage and the document table, but are not linked to the
#   quotation and do not produce extraction results, pending a bigger design decision
#   (either a join table, or one quotation per attachment).
# - Storage path reuses the EXISTING `document.storage_path` shape
#   (`tenants/{tenant_id}/quotations/{document_id}/{filename}`), not the
#   `{tenant_id}/ingestion/email/...` shape data-model.md proposed — the `document` table's own
#   `document_storage_path_tenant_prefixed` CHECK constraint only allows the former, and widening
#   it for no functional reason (source_channel already distinguishes provenance) would be
#   invasive for no benefit.


def process_inbound_email(
    settings: Settings,
    *,
    tenant_id: UUID,
    raw_email_bytes: bytes,
    raw_email_ref: str | None,
) -> dict[str, object]:
    try:
        email_data = parse_email(raw_email_bytes)
    except EmailParseError as exc:
        logger.error("Failed to parse inbound email for tenant %s: %s", tenant_id, exc)
        return {"status": "rejected", "reason": str(exc)}

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _act_as_tenant(conn, tenant_id)

        log_id = _insert_email_log_row(
            conn, tenant_id=tenant_id, email_data=email_data, raw_email_ref=raw_email_ref
        )
        if log_id is None:
            conn.commit()
            _record_audit(
                tenant_id=tenant_id,
                action="email_duplicate",
                target={"message_id": email_data.message_id},
                outcome="success",
            )
            return {"status": "duplicate", "message_id": email_data.message_id}

        rejection = _validate_content(settings, email_data)
        if rejection is not None:
            _mark_log_terminal(conn, log_id, status="rejected", error_message=rejection)
            conn.commit()
            _record_audit(
                tenant_id=tenant_id,
                action="email_rejected",
                target={"message_id": email_data.message_id, "reason": rejection},
                outcome="refused",
            )
            return {"status": "rejected", "reason": rejection}

        supplier_id, match_method = match_supplier(
            conn,
            tenant_id=tenant_id,
            from_address=email_data.from_address,
            from_domain=email_data.from_domain,
            in_reply_to=email_data.in_reply_to,
            references=email_data.references,
        )

        document_id, mime_type, filename = _store_primary_document(
            settings, conn, tenant_id=tenant_id, email_data=email_data
        )

        quotation_id = _insert_quotation(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            supplier_id=supplier_id,
            ingestion_email_id=log_id,
        )

        job_id = _insert_extraction_job(conn, tenant_id=tenant_id, quotation_id=quotation_id)

        _mark_log_completed(
            conn,
            log_id,
            quotation_id=quotation_id,
            supplier_id=supplier_id,
            match_method=match_method,
            attachment_count=len(email_data.attachments),
        )
        conn.commit()

    try:
        _enqueue_extraction(
            settings,
            job_id=job_id,
            tenant_id=tenant_id,
            quotation_id=quotation_id,
            document_id=document_id,
        )
    except Exception:
        logger.exception("Failed to enqueue extraction for quotation %s", quotation_id)
        # The quotation and document are already durably created; a failed enqueue is retryable
        # via the existing retry_extraction endpoint, matching how a manually-uploaded quotation
        # recovers from the same failure mode (quotations/service.py's own _enqueue_extraction).

    _record_audit(
        tenant_id=tenant_id,
        action="email_received",
        target={
            "message_id": email_data.message_id,
            "quotation_id": str(quotation_id),
            "attachment_count": len(email_data.attachments),
        },
        outcome="success",
    )
    _record_audit(
        tenant_id=tenant_id,
        action="email_supplier_matched" if supplier_id else "email_supplier_unmatched",
        target={"quotation_id": str(quotation_id), "match_method": match_method},
        outcome="success",
    )

    if supplier_id is None:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            _act_as_tenant(conn, tenant_id)
            _insert_unmatched_review_task(conn, tenant_id=tenant_id, quotation_id=quotation_id)
            conn.commit()

    return {
        "status": "completed",
        "quotation_id": str(quotation_id),
        "document_id": str(document_id),
        "supplier_id": str(supplier_id) if supplier_id else None,
        "match_method": match_method,
    }


def _act_as_tenant(conn: psycopg.Connection, tenant_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"tenant_id": str(tenant_id), "role": "authenticated"}),),
        )


def _validate_content(settings: Settings, email_data: InboundEmail) -> str | None:
    if not email_data.attachments and not email_data.body_text:
        return "empty_email_no_content"

    total_bytes = sum(a.size_bytes for a in email_data.attachments)
    if total_bytes > settings.ingestion_max_email_bytes:
        return "email_too_large"

    for attachment in email_data.attachments:
        if attachment.size_bytes > settings.ingestion_max_attachment_bytes:
            return "attachment_too_large"
        if attachment.content_type_mismatch:
            return "attachment_content_type_mismatch"

    return None


def _insert_email_log_row(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    email_data: InboundEmail,
    raw_email_ref: str | None,
) -> UUID | None:
    """Returns the new row's id, or None if this message_id was already processed for this
    tenant (R4) — the unique constraint is the authoritative dedup check, not a pre-check
    query, so a race between two webhook deliveries of the same email can never both succeed."""
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into ingestion_email_log
                  (tenant_id, message_id, from_address, from_domain, subject, in_reply_to,
                   references_list, status, attachment_count, raw_email_ref)
                values (%(tenant_id)s, %(message_id)s, %(from_address)s, %(from_domain)s,
                        %(subject)s, %(in_reply_to)s, %(references_list)s, 'processing',
                        %(attachment_count)s, %(raw_email_ref)s)
                returning id
                """,
                {
                    "tenant_id": tenant_id,
                    "message_id": email_data.message_id,
                    "from_address": email_data.from_address,
                    "from_domain": email_data.from_domain,
                    "subject": email_data.subject,
                    "in_reply_to": email_data.in_reply_to,
                    "references_list": email_data.references,
                    "attachment_count": len(email_data.attachments),
                    "raw_email_ref": raw_email_ref,
                },
            )
            row = cur.fetchone()
        return UUID(str(row["id"]))
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        return None


def _mark_log_terminal(
    conn: psycopg.Connection, log_id: UUID, *, status: str, error_message: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update ingestion_email_log
            set status = %s, error_message = %s, processed_at = now()
            where id = %s
            """,
            (status, error_message, log_id),
        )


def _mark_log_completed(
    conn: psycopg.Connection,
    log_id: UUID,
    *,
    quotation_id: UUID,
    supplier_id: UUID | None,
    match_method: str | None,
    attachment_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update ingestion_email_log
            set status = 'completed',
                processed_at = now(),
                quotation_id = %s,
                supplier_id = %s,
                match_method = %s,
                attachment_count = %s
            where id = %s
            """,
            (quotation_id, supplier_id, match_method, attachment_count, log_id),
        )


def _primary_content(email_data: InboundEmail) -> tuple[bytes, str, str]:
    """Returns (content, mime_type, filename) for whichever attachment (the first) or the body
    text becomes the quotation's one primary document."""
    if email_data.attachments:
        attachment: ParsedAttachment = email_data.attachments[0]
        return attachment.content, attachment.declared_content_type, attachment.filename
    body = (email_data.body_text or "").encode("utf-8")
    return body, "text/plain", "email-body.txt"


def _store_primary_document(
    settings: Settings,
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    email_data: InboundEmail,
) -> tuple[UUID, str, str]:
    content, mime_type, filename = _primary_content(email_data)
    document_id = uuid4()
    storage_path = f"tenants/{tenant_id}/quotations/{document_id}/{filename}"
    bucket = settings.quotation_documents_bucket

    client = create_client(
        settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
    )
    client.storage.from_(bucket).upload(
        storage_path, content, {"content-type": mime_type, "upsert": "true"}
    )

    content_hash = hashlib.sha256(content).hexdigest()
    with conn.cursor() as cur:
        # `document.created_by` is NOT NULL — there is no human actor for a system-ingested
        # document, so it is attributed to whichever member configured email ingestion for this
        # tenant (tenant_email_config.created_by), the closest real accountable party.
        cur.execute(
            """
            insert into document
              (id, tenant_id, storage_bucket, storage_path, mime_type, content_hash,
               source_channel, status, created_by)
            values (%s, %s, %s, %s, %s, %s, 'email', 'uploaded',
                    (select created_by from tenant_email_config where tenant_id = %s))
            """,
            (document_id, tenant_id, bucket, storage_path, mime_type, content_hash, tenant_id),
        )

    _store_secondary_documents(
        settings,
        conn,
        client=client,
        tenant_id=tenant_id,
        attachments=email_data.attachments[1:],
    )

    return document_id, mime_type, filename


def _store_secondary_documents(
    settings: Settings,
    conn: psycopg.Connection,
    *,
    client: Client,
    tenant_id: UUID,
    attachments: list[ParsedAttachment],
) -> None:
    bucket = settings.quotation_documents_bucket
    for attachment in attachments:
        try:
            document_id = uuid4()
            storage_path = f"tenants/{tenant_id}/quotations/{document_id}/{attachment.filename}"
            client.storage.from_(bucket).upload(
                storage_path,
                attachment.content,
                {"content-type": attachment.declared_content_type, "upsert": "true"},
            )
            content_hash = hashlib.sha256(attachment.content).hexdigest()
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into document
                          (id, tenant_id, storage_bucket, storage_path, mime_type, content_hash,
                           source_channel, status, created_by)
                        values (%s, %s, %s, %s, %s, %s, 'email', 'uploaded',
                                (select created_by from tenant_email_config where tenant_id = %s))
                        """,
                        (
                            document_id,
                            tenant_id,
                            bucket,
                            storage_path,
                            attachment.declared_content_type,
                            content_hash,
                            tenant_id,
                        ),
                    )
        except Exception:
            logger.warning(
                "Failed to store secondary attachment %s for tenant %s; continuing",
                attachment.filename,
                tenant_id,
                exc_info=True,
            )


def _insert_quotation(
    conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    document_id: UUID,
    supplier_id: UUID | None,
    ingestion_email_id: UUID,
) -> UUID:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            insert into quotation
              (tenant_id, document_id, supplier_id, status, source, ingestion_email_id)
            values (%s, %s, %s, 'pending', 'email', %s)
            returning id
            """,
            (tenant_id, document_id, supplier_id, ingestion_email_id),
        )
        row = cur.fetchone()
    return UUID(str(row["id"]))


def _insert_extraction_job(
    conn: psycopg.Connection, *, tenant_id: UUID, quotation_id: UUID
) -> UUID:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            insert into extraction_job (tenant_id, quotation_id, status)
            values (%s, %s, 'queued')
            returning id
            """,
            (tenant_id, quotation_id),
        )
        row = cur.fetchone()
    return UUID(str(row["id"]))


def _insert_unmatched_review_task(
    conn: psycopg.Connection, *, tenant_id: UUID, quotation_id: UUID
) -> None:
    # No review_task_reason value names "supplier unmatched" specifically; 'review_required' is
    # the closest existing generic fit and adding a new enum value for one reason string is not
    # worth another migration.
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into review_task (tenant_id, quotation_id, status, priority, reason)
            values (%s, %s, 'open', 'normal', 'review_required')
            on conflict do nothing
            """,
            (tenant_id, quotation_id),
        )


def _record_audit(
    *, tenant_id: UUID, action: str, target: dict[str, object], outcome: AuditOutcome
) -> None:
    try:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=tenant_id,
                actor_email="ingestion-worker@procurepilot.local",
                action=action,
                target=target,
                outcome=outcome,
                trace_id=get_trace_id(),
            )
        )
    except Exception:
        logger.exception("Failed to record ingestion audit event: %s", action)
