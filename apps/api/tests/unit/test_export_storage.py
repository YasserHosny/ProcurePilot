from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr

from procurepilot_api.modules.exports.storage import ExportStorage


class _Bucket:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, dict[str, str]]] = []

    def upload(self, path: str, content: bytes, options: dict[str, str]) -> None:
        self.uploads.append((path, content, options))


class _Storage:
    def __init__(self, bucket: _Bucket) -> None:
        self.bucket = bucket
        self.name: str | None = None

    def from_(self, name: str) -> _Bucket:
        self.name = name
        return self.bucket


class _Client:
    def __init__(self, storage: _Storage) -> None:
        self.storage = storage


class _Settings:
    supabase_url = "http://supabase.test"
    supabase_service_role_key = SecretStr("service-role")
    supabase_exports_bucket = "exports"


def test_export_upload_uses_exports_bucket_and_tenant_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = _Bucket()
    storage = _Storage(bucket)
    monkeypatch.setattr(
        "procurepilot_api.modules.exports.storage.create_client",
        lambda *_args: _Client(storage),
    )
    tenant_id = uuid4()
    job_id = uuid4()

    result = ExportStorage(_Settings()).upload(
        tenant_id=tenant_id,
        job_id=job_id,
        format="xlsx",
        content=b"data",
    )

    assert result == (
        "exports",
        f"{tenant_id}/savings/{job_id}.xlsx",
        f"/api/v1/exports/{job_id}/download",
    )
    assert storage.name == "exports"
    assert bucket.uploads[0][0] == f"{tenant_id}/savings/{job_id}.xlsx"
