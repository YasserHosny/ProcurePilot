from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from integration.value_proof_helpers import export_request, fetch_export_jobs, record_purchase
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.exports import service as export_service_module
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.savings.service import SavingsService
from procurepilot_api.workers import export_worker

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class _NoAuditWriter:
    """create_job records `reports.export_requested` (R2.5 contract); these tests exercise
    the queue/durability behaviour, not the audit trail."""

    def record(self, event: object, bearer_token: str | None = None) -> None:
        return None


def test_export_create_queues_durable_job_without_tenant_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-queued") as context:
        enqueued: list[tuple[UUID, UUID]] = []

        def fake_enqueue(_settings: object, row: dict[str, object], member: object) -> None:
            enqueued.append((UUID(str(row["id"])), member.tenant_id))

        monkeypatch.setattr(export_service_module, "_enqueue_export_job", fake_enqueue)
        monkeypatch.setattr(export_service_module, "get_audit_writer", lambda: _NoAuditWriter())
        job = ExportService(settings).create_job(
            member=context.member,
            payload=export_request(),
        )

        assert job.status == "queued"
        assert enqueued == [(job.id, context.workspace.tenant_id)]
        assert fetch_export_jobs(context.workspace.tenant_id)[0]["id"] == job.id


def test_verified_savings_export_query_excludes_pending_and_handles_empty_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-verified-only") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        service = SavingsService(settings)
        verified = record_purchase(service, context, actual="8.0000")
        service.verify_saving(member=context.member, saving_id=verified.id)
        record_purchase(service, context, actual="9.0000")

        with _authenticated_db(settings, context.member) as conn:
            rows = export_worker._fetch_report_rows(
                conn,
                tenant_id=context.workspace.tenant_id,
                kind="savings_ledger",
                filters={
                    "period_start": "2026-01-01",
                    "period_end": "2026-12-31",
                    "supplier_id": None,
                    "branch_id": None,
                },
            )
            empty = export_worker._fetch_report_rows(
                conn,
                tenant_id=context.workspace.tenant_id,
                kind="savings_ledger",
                filters={
                    "period_start": "2000-01-01",
                    "period_end": "2000-12-31",
                    "supplier_id": None,
                    "branch_id": None,
                },
            )

        assert [row["saving_id"] for row in rows] == [verified.id]
        assert empty == []


def test_cross_tenant_export_read_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-alpha") as alpha:
        with committed_smart_context("export-beta") as beta:
            monkeypatch.setattr(
                export_service_module,
                "_enqueue_export_job",
                lambda *_args, **_kwargs: None,
            )
            monkeypatch.setattr(export_service_module, "get_audit_writer", lambda: _NoAuditWriter())
            job = ExportService(settings).create_job(member=alpha.member, payload=export_request())

            with pytest.raises(NotFoundError):
                ExportService(settings).get_job(member=beta.member, job_id=job.id)


def test_enqueue_failure_persists_failed_status_from_separate_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-enqueue-fails") as context:
        monkeypatch.setattr(
            export_service_module,
            "_enqueue_export_job",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ServiceUnavailableError(details={"dependency": "redis"})
            ),
        )

        with pytest.raises(ServiceUnavailableError):
            ExportService(settings).create_job(member=context.member, payload=export_request())

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, error from export_job where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                row = cur.fetchone()
        assert row["status"] == "failed"
        assert row["error"]["code"] == "redis_enqueue_failed"


def test_worker_failure_persists_failed_status_from_separate_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-worker-fails") as context:
        monkeypatch.setattr(
            export_service_module,
            "_enqueue_export_job",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(export_service_module, "get_audit_writer", lambda: _NoAuditWriter())
        job = ExportService(settings).create_job(member=context.member, payload=export_request())
        monkeypatch.setattr(
            export_worker,
            "render_xlsx",
            lambda _rows, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced-render-failure")),
        )
        monkeypatch.setattr(export_worker, "get_settings", lambda: settings)

        with pytest.raises(RuntimeError, match="forced-render-failure"):
            export_worker.process_export_job(
                {"job_id": str(job.id), "tenant_id": str(context.workspace.tenant_id)}
            )

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status, error from export_job where id = %s", (job.id,))
                row = cur.fetchone()
        assert row["status"] == "failed"
        assert row["error"]["code"] == "export_render_failed"
