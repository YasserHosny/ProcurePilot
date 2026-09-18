from __future__ import annotations

from uuid import UUID, uuid4

import magic
from psycopg.rows import dict_row
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    NotFoundError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.ingestion.extraction import enqueue_extraction
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, AuditOutcome, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

# T015 (research R5): a dedicated capture endpoint, synchronous within the request — there is no
# external step to decouple from (the server already has the file bytes from the multipart
# upload), so this mirrors the manual-upload flow's own document+quotation+extraction_job
# creation rather than routing through `ingestion_jobs` the way email (an externally-triggered,
# webhook-driven channel) needs to.

_ACCEPTED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic"}


class CaptureService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_capture(
        self,
        *,
        member: CurrentMember,
        file_content: bytes,
        filename: str,
        supplier_id: UUID | None,
        notes: str | None,
        bearer_token: str | None = None,
    ) -> dict[str, object]:
        if len(file_content) > self._settings.capture_max_bytes:
            self._record_audit(
                bearer_token=bearer_token,
                member=member,
                action="capture_rejected",
                target={"reason": "file_too_large"},
                outcome="refused",
            )
            raise UnprocessableEntityError(details={"reason": "file_too_large"})

        detected_mime = magic.from_buffer(file_content, mime=True)
        if detected_mime not in _ACCEPTED_MIME_TYPES:
            self._record_audit(
                bearer_token=bearer_token,
                member=member,
                action="capture_rejected",
                target={"reason": "unsupported_file_type", "detected_mime": detected_mime},
                outcome="refused",
            )
            raise UnsupportedMediaTypeError(details={"detected_mime": detected_mime})

        with _authenticated_db(self._settings, member) as conn:
            if supplier_id is not None:
                with conn.cursor() as cur:
                    cur.execute("select 1 from supplier where id = %s", (supplier_id,))
                    if cur.fetchone() is None:
                        raise NotFoundError(details={"resource": "supplier"})

            document_id = uuid4()
            storage_path = f"tenants/{member.tenant_id}/quotations/{document_id}/{filename}"
            client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
            client.storage.from_(self._settings.quotation_documents_bucket).upload(
                storage_path, file_content, {"content-type": detected_mime, "upsert": "true"}
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into document
                      (id, tenant_id, storage_bucket, storage_path, mime_type, source_channel,
                       status, created_by)
                    values (%s, %s, %s, %s, %s, 'capture', 'uploaded', %s)
                    """,
                    (
                        document_id,
                        member.tenant_id,
                        self._settings.quotation_documents_bucket,
                        storage_path,
                        detected_mime,
                        member.membership_id,
                    ),
                )

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into quotation (tenant_id, document_id, supplier_id, status, source)
                    values (%s, %s, %s, 'pending', 'capture')
                    returning id
                    """,
                    (member.tenant_id, document_id, supplier_id),
                )
                quotation_id = UUID(str(cur.fetchone()["id"]))

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into extraction_job (tenant_id, quotation_id, status)
                    values (%s, %s, 'queued')
                    returning id
                    """,
                    (member.tenant_id, quotation_id),
                )
                job_id = UUID(str(cur.fetchone()["id"]))

            conn.commit()

        try:
            enqueue_extraction(
                self._settings,
                job_id=job_id,
                tenant_id=member.tenant_id,
                quotation_id=quotation_id,
                document_id=document_id,
            )
        except Exception:
            # Durably created already; retryable via the existing retry_extraction endpoint,
            # same recovery path a manually-uploaded quotation has for the identical failure.
            pass

        self._record_audit(
            bearer_token=bearer_token,
            member=member,
            action="capture_uploaded",
            target={
                "quotation_id": str(quotation_id),
                "document_id": str(document_id),
                "supplier_id": str(supplier_id) if supplier_id else None,
                # No persisted column for free-text notes on `quotation` exists yet — carried in
                # the audit trail rather than silently dropped.
                "notes": notes,
            },
            outcome="success",
        )

        return {"quotation_id": quotation_id, "status": "pending"}

    def _record_audit(
        self,
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


def get_capture_service() -> CaptureService:
    return CaptureService()
