from __future__ import annotations

from uuid import UUID

from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ServiceUnavailableError


class ExportStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def upload(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        format: str,
        content: bytes,
    ) -> tuple[str, str, str]:
        bucket = self._settings.supabase_exports_bucket
        path = f"{tenant_id}/savings/{job_id}.{format}"
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if format == "xlsx"
            else "application/pdf"
        )
        try:
            client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
            client.storage.from_(bucket).upload(
                path,
                content,
                {"content-type": content_type, "upsert": "true"},
            )
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        return bucket, path, f"/api/v1/exports/{job_id}/download"

    def create_signed_url(self, *, bucket: str, path: str, ttl_seconds: int) -> str:
        try:
            client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
            result = client.storage.from_(bucket).create_signed_url(path, expires_in=ttl_seconds)
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        return str(result["signedURL"])


def get_export_storage() -> ExportStorage:
    return ExportStorage()
