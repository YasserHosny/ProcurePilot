from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    NotFoundError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.documents.schemas import Document, PresignRequest, PresignResponse
from procurepilot_api.modules.members.service import authenticated_client

ACCEPTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

DOCUMENT_COLUMNS = (
    "id,storage_bucket,storage_path,mime_type,content_hash,source_channel,status,created_at,"
    "created_by"
)


class DocumentService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_presigned_upload(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: PresignRequest,
    ) -> PresignResponse:
        if payload.mime_type not in ACCEPTED_MIME_TYPES:
            raise UnsupportedMediaTypeError(details={"mime_type": "unsupported"})

        client = authenticated_client(self._settings, bearer_token)
        bucket = self._settings.quotation_documents_bucket
        document_id = uuid4()
        storage_path = _storage_path(
            tenant_id=member.tenant_id,
            document_id=document_id,
            filename=payload.filename,
        )
        try:
            response = client.table("document").insert(
                {
                    "id": str(document_id),
                    "tenant_id": str(member.tenant_id),
                    "storage_bucket": bucket,
                    "storage_path": storage_path,
                    "mime_type": payload.mime_type,
                    "content_hash": payload.content_hash,
                    "source_channel": "upload",
                    "status": "uploaded",
                    "created_by": str(member.membership_id),
                }
            ).execute()
            row = _one_row(response.data, resource="document")
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        return PresignResponse(
            document_id=UUID(str(row["id"])),
            storage_bucket=bucket,
            storage_path=str(row["storage_path"]),
            upload_url=_signed_upload_url(self._settings, bucket, str(row["storage_path"])),
            upload_fields={},
            expires_at=expires_at,
        )

    def get_document(self, *, bearer_token: str, document_id: UUID) -> Document:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("document")
                .select(DOCUMENT_COLUMNS)
                .eq("id", str(document_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return Document.model_validate(_one_row(response.data, resource="document"))


def get_document_service() -> DocumentService:
    return DocumentService()


def _storage_path(*, tenant_id: UUID, document_id: UUID, filename: str) -> str:
    name = PurePosixPath(filename).name.replace("/", "_")
    return f"tenants/{tenant_id}/quotations/{document_id}/{name}"


def _signed_upload_url(settings: Settings, bucket: str, path: str) -> str:
    base = settings.supabase_url.rstrip("/")
    # Local stub upload target. The Storage service remains the intended direct-upload boundary;
    # real signed upload token plumbing can replace this call without changing API shape.
    return f"{base}/storage/v1/object/{bucket}/{path}"


def _one_row(data: object, *, resource: str) -> dict[str, object]:
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    raise NotFoundError(details={"resource": resource})
