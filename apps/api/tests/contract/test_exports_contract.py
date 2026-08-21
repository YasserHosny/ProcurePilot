from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters, ExportJob


def test_export_create_shape_rejects_tenant_id_and_validates_branch_placeholder() -> None:
    payload = {
        "kind": "savings_ledger",
        "format": "xlsx",
        "filters": {"period_start": "2026-08-01", "period_end": "2026-08-31"},
        "tenant_id": str(uuid4()),
    }
    with pytest.raises(ValidationError):
        ExportCreate.model_validate(payload)

    del payload["tenant_id"]
    request = ExportCreate.model_validate(payload)
    assert request.kind == "savings_ledger"
    assert request.filters.branch_id is None


def test_export_filters_reject_inverted_period() -> None:
    with pytest.raises(ValidationError):
        ExportFilters(period_start="2026-08-31", period_end="2026-08-01")


def test_export_job_shape_supports_terminal_status_and_download_url() -> None:
    job = ExportJob(
        id=uuid4(),
        kind="savings_ledger",
        format="pdf",
        filters=ExportFilters(period_start="2026-08-01", period_end="2026-08-31"),
        status="completed",
        row_count=0,
        download_url="/api/v1/exports/test/download",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )

    body = job.model_dump(mode="json")
    assert body["status"] == "completed"
    assert body["row_count"] == 0
