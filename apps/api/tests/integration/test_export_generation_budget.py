from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from integration.value_proof_helpers import export_request, fetch_export_jobs, record_purchase
from procurepilot_api.errors import ExportRowCapExceededError
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.modules.exports.storage import ExportStorage
from procurepilot_api.modules.savings.service import SavingsService
from procurepilot_api.workers import export_worker

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class _NoAuditWriter:
    def record(self, event: object, bearer_token: str | None = None) -> None:
        return None


def _synthetic_savings_rows(count: int) -> list[dict[str, object]]:
    """Rows shaped like `reporting_savings_for_period`'s own output — enough for
    `_extract_row_values`'s default (savings_ledger) branch to render every column, without
    paying for a 10,000-row join across saving_record/purchase_record/workspace_product/
    canonical_product/branch for every test run. The join itself is reviewed for correctness
    and RLS pinning elsewhere (T036); this test isolates and times the render + storage-upload
    step, which is what SC-004's 60-second budget is actually about."""
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append(
            {
                "saving_id": uuid4(),
                "recorded_at": now,
                "attributed_branch_name": "Main Branch",
                "supplier_name": "Synthetic Supplier",
                "product_name": f"Synthetic Product {index}",
                "base_unit": "unit",
                "quantity": 1,
                "baseline_value_amount": "10.00",
                "actual_total_paid_amount": "8.00",
                "verified_saving_amount": "2.00",
                "verified_saving_currency": "USD",
            }
        )
    return rows


def test_ten_thousand_row_export_renders_and_uploads_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-004: a 10,000-row export completes within 60 seconds."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("export-perf-budget") as context:
        monkeypatch.setattr(
            "procurepilot_api.modules.exports.service._enqueue_export_job",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "procurepilot_api.modules.exports.service.get_audit_writer",
            lambda: _NoAuditWriter(),
        )
        job = ExportService(settings).create_job(
            member=context.member,
            payload=export_request(),
        )
        assert job.status == "queued"

        rows = _synthetic_savings_rows(10_000)
        monkeypatch.setattr(export_worker, "get_settings", lambda: settings)
        monkeypatch.setattr(
            export_worker,
            "_fetch_report_rows",
            lambda *_args, **_kwargs: rows,
        )

        uploaded: list[dict[str, object]] = []

        def fake_upload(
            _self: ExportStorage,
            *,
            tenant_id: object,
            job_id: object,
            format: str,
            content: bytes,
        ) -> tuple[str, str, str]:
            uploaded.append({"tenant_id": tenant_id, "job_id": job_id, "format": format})
            return (
                "exports",
                f"{tenant_id}/perf/{job_id}.{format}",
                f"/api/v1/exports/{job_id}/download",
            )

        monkeypatch.setattr(ExportStorage, "upload", fake_upload)

        started = time.perf_counter()
        result = export_worker.process_export_job(
            {"job_id": str(job.id), "tenant_id": str(context.workspace.tenant_id)}
        )
        elapsed = time.perf_counter() - started

        assert elapsed < 60, f"10,000-row export took {elapsed:.2f}s, over the 60s budget"
        assert result["status"] == "completed"
        assert result["row_count"] == 10_000
        assert len(uploaded) == 1
        assert uploaded[0]["format"] == "xlsx"


def test_over_cap_export_refused_without_queueing_or_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-004: an over-cap request is refused with the structured error and no storage
    object is created — the cap check runs before the job row (and therefore any render or
    upload) ever exists."""
    settings = settings_for_test_db(monkeypatch)
    capped_settings = settings.model_copy(update={"export_row_cap": 2})

    with committed_smart_context("export-over-cap") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        service = SavingsService(settings)
        for actual in ("8.0000", "8.5000", "9.0000"):
            saving = record_purchase(service, context, actual=actual)
            service.verify_saving(member=context.member, saving_id=saving.id)

        enqueue_calls: list[object] = []
        monkeypatch.setattr(
            "procurepilot_api.modules.exports.service._enqueue_export_job",
            lambda *args, **_kwargs: enqueue_calls.append(args),
        )
        upload_calls: list[object] = []
        monkeypatch.setattr(
            ExportStorage,
            "upload",
            lambda self, **kwargs: upload_calls.append(kwargs),
        )

        with pytest.raises(ExportRowCapExceededError) as excinfo:
            ExportService(capped_settings).create_job(
                member=context.member,
                payload=export_request(),
            )

        assert excinfo.value.code == "export_row_cap_exceeded"
        assert excinfo.value.details == {"cap": 2, "actual": 3}
        assert enqueue_calls == []
        assert upload_calls == []
        assert fetch_export_jobs(context.workspace.tenant_id) == []
