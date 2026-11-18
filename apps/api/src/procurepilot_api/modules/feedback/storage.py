"""Storage access for feedback attachments (spec 025, research D5).

The member's own token uploads (the bucket policy allows INSERT only, under the member's tenant
prefix, and `upsert=false` means an existing object is never overwritten). Reads, deletes and
signing run with the service-role client, and only after the caller has passed the row-level
check on the attachment row, so a leaked path is useless on its own.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID, uuid4

from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.shared.storage_keys import safe_object_name

logger = logging.getLogger(__name__)

type ClientFactory = Callable[[str, str], Client]


def attachment_storage_path(*, tenant_id: UUID, submission_id: UUID, filename: str) -> str:
    """`tenants/{tenant_id}/feedback/{submission_id}/{uuid}/{safe_object_name}`.

    The tenant id is the second path segment, which is what the bucket policy checks.
    """
    return f"tenants/{tenant_id}/feedback/{submission_id}/{uuid4()}/{safe_object_name(filename)}"


def extract_signed_url(result: object) -> str:
    if isinstance(result, str) and result:
        return result
    if isinstance(result, dict):
        for key in ("signedURL", "signedUrl", "signed_url", "url"):
            value = result.get(key)
            if value:
                return str(value)
    raise ServiceUnavailableError(details={"dependency": "supabase_storage"})


class FeedbackStorage:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client_factory: ClientFactory = client_factory or create_client

    @property
    def bucket(self) -> str:
        return self._settings.feedback_bucket

    def upload(self, *, bearer_token: str, path: str, content: bytes, content_type: str) -> None:
        """Upload one object as the caller. Never overwrites."""
        try:
            client = self._client_factory(
                self._settings.supabase_url,
                self._settings.supabase_anon_key.get_secret_value(),
            )
            # supabase-py only authorises PostgREST from `postgrest.auth`; the storage session
            # carries its own headers, so the caller's token is set there explicitly.
            client.storage.session.headers["Authorization"] = f"Bearer {bearer_token}"
            client.storage.from_(self.bucket).upload(
                path,
                content,
                {"content-type": content_type, "upsert": "false"},
            )
        except Exception as exc:
            logger.warning("Feedback attachment upload failed", exc_info=True)
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc

    def delete(self, paths: Sequence[str]) -> list[str]:
        """Best-effort delete with the service role; returns the paths that could not be removed.

        Never raises: callers run this on a failure path or after the row is already gone, and
        anything left behind is removed by the orphan sweep.
        """
        if not paths:
            return []
        try:
            client = self._service_client()
            client.storage.from_(self.bucket).remove(list(paths))
        except Exception:
            logger.warning(
                "Feedback attachment delete failed; the orphan sweep will remove them",
                extra={"object_count": len(paths)},
                exc_info=True,
            )
            return list(paths)
        return []

    def signed_url(self, path: str) -> str:
        try:
            result: Any = (
                self._service_client()
                .storage.from_(self.bucket)
                .create_signed_url(
                    path, expires_in=self._settings.feedback_attachment_url_ttl_seconds
                )
            )
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        return extract_signed_url(result)

    def _service_client(self) -> Client:
        return self._client_factory(
            self._settings.supabase_url,
            self._settings.supabase_service_role_key.get_secret_value(),
        )
