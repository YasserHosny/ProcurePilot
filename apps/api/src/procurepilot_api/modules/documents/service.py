from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    NotFoundError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.documents.schemas import (
    Document,
    DownloadUrlResponse,
    PotentialDuplicate,
    PresignRequest,
    PresignResponse,
)
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

        potential_duplicates = _potential_duplicates(
            client=client,
            content_hash=payload.content_hash,
            document_id=document_id,
        )
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        return PresignResponse(
            document_id=UUID(str(row["id"])),
            storage_bucket=bucket,
            storage_path=str(row["storage_path"]),
            upload_url=_signed_upload_url(self._settings, bucket, str(row["storage_path"])),
            upload_fields={},
            expires_at=expires_at,
            potential_duplicates=potential_duplicates,
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

    def create_download_url(self, *, bearer_token: str, document_id: UUID) -> DownloadUrlResponse:
        doc = self.get_document(bearer_token=bearer_token, document_id=document_id)
        try:
            client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
            result = client.storage.from_(doc.storage_bucket).create_signed_url(
                doc.storage_path,
                expires_in=300,
            )
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc

        return DownloadUrlResponse(download_url=str(result["signedURL"]))


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


def _potential_duplicates(
    *,
    client: object,
    content_hash: str | None,
    document_id: UUID,
) -> list[PotentialDuplicate]:
    if not content_hash:
        return []

    try:
        document_response = (
            client.table("document")
            .select("id")
            .eq("content_hash", content_hash)
            .neq("id", str(document_id))
            .limit(5)
            .execute()
        )
        document_ids = [
            str(row["id"])
            for row in _rows(document_response.data)
            if isinstance(row.get("id"), str)
        ]
        if not document_ids:
            return []

        quotation_response = (
            client.table("quotation")
            .select(
                "id,document_id,created_at,stated_total_amount,stated_total_currency,supplier(name)"
            )
            .in_("document_id", document_ids)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
    except APIError:
        return []

    return [_potential_duplicate(row) for row in _rows(quotation_response.data)]


def _potential_duplicate(row: dict[str, object]) -> PotentialDuplicate:
    supplier = row.get("supplier")
    supplier_name = supplier.get("name") if isinstance(supplier, dict) else None
    return PotentialDuplicate(
        quotation_id=UUID(str(row["id"])),
        document_id=UUID(str(row["document_id"])),
        created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
        supplier_name=str(supplier_name) if supplier_name else None,
        stated_total_amount=_string_or_none(row.get("stated_total_amount")),
        stated_total_currency=_string_or_none(row.get("stated_total_currency")),
    )


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
