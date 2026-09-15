from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    SmartCompareContext,
    committed_smart_context,
    settings_for_test_db,
)
from integration.value_proof_helpers import export_request
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.exports import service as export_service_module
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.modules.exports.storage import ExportStorage
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _insert_completed_job(
    context: SmartCompareContext,
    *,
    format: str = "xlsx",
    row_count: int = 5,
) -> UUID:
    with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into export_job (tenant_id, requested_by, kind, format, filters, status)
                values (%s, %s, 'savings_ledger', %s, %s, 'queued')
                returning id
                """,
                (
                    context.workspace.tenant_id,
                    context.member.membership_id,
                    format,
                    Jsonb(export_request().filters.model_dump(mode="json")),
                ),
            )
            job_id = UUID(str(dict(cur.fetchone())["id"]))
            cur.execute(
                """
                update export_job
                set status = 'completed',
                    row_count = %s,
                    storage_bucket = 'exports',
                    storage_path = %s,
                    download_url = %s,
                    completed_at = now()
                where id = %s
                """,
                (
                    row_count,
                    f"{context.workspace.tenant_id}/savings/{job_id}.{format}",
                    f"/api/v1/exports/{job_id}/download",
                    job_id,
                ),
            )
    return job_id


def test_download_returns_signed_url_and_audits_for_completed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-download-ok") as context:
        job_id = _insert_completed_job(context)

        signed_calls: list[dict[str, object]] = []

        def fake_signed_url(
            _self: ExportStorage, *, bucket: str, path: str, ttl_seconds: int
        ) -> str:
            signed_calls.append({"bucket": bucket, "path": path, "ttl_seconds": ttl_seconds})
            return f"https://storage.example.fake/signed/{bucket}/{path}"

        monkeypatch.setattr(ExportStorage, "create_signed_url", fake_signed_url)

        audit_events: list[AuditEventCreate] = []

        class FakeAuditWriter:
            def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
                audit_events.append(event)

        monkeypatch.setattr(export_service_module, "get_audit_writer", lambda: FakeAuditWriter())

        url = ExportService(settings).create_download_url(
            member=context.member,
            job_id=job_id,
            bearer_token="caller-token",
        )

        assert url == (
            f"https://storage.example.fake/signed/exports/"
            f"{context.workspace.tenant_id}/savings/{job_id}.xlsx"
        )
        assert signed_calls == [
            {
                "bucket": "exports",
                "path": f"{context.workspace.tenant_id}/savings/{job_id}.xlsx",
                "ttl_seconds": settings.export_download_url_ttl_seconds,
            }
        ]
        assert [event.action for event in audit_events] == ["reports.artifact_downloaded"]
        assert audit_events[0].tenant_id == context.workspace.tenant_id
        assert audit_events[0].actor_membership_id == context.member.membership_id
        assert audit_events[0].target == {
            "export_job_id": str(job_id),
            "kind": "savings_ledger",
            "format": "xlsx",
            "row_count": 5,
        }


def test_download_for_job_without_artifact_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-download-queued") as context:
        monkeypatch.setattr(
            export_service_module,
            "_enqueue_export_job",
            lambda *_args, **_kwargs: None,
        )
        job = ExportService(settings).create_job(
            member=context.member,
            payload=export_request(),
        )

        with pytest.raises(NotFoundError):
            ExportService(settings).create_download_url(
                member=context.member,
                job_id=job.id,
                bearer_token="caller-token",
            )


def test_download_cross_tenant_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-download-alpha") as alpha:
        with committed_smart_context("export-download-beta") as beta:
            job_id = _insert_completed_job(alpha)

            def fake_signed_url(
                _self: ExportStorage, *, bucket: str, path: str, ttl_seconds: int
            ) -> str:
                raise AssertionError("signed URL must never be minted cross-tenant")

            monkeypatch.setattr(ExportStorage, "create_signed_url", fake_signed_url)

            with pytest.raises(NotFoundError):
                ExportService(settings).create_download_url(
                    member=beta.member,
                    job_id=job_id,
                    bearer_token="caller-token",
                )


def test_download_for_missing_job_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-download-missing") as context:
        with pytest.raises(NotFoundError):
            ExportService(settings).create_download_url(
                member=context.member,
                job_id=UUID("00000000-0000-0000-0000-000000000000"),
                bearer_token="caller-token",
            )
