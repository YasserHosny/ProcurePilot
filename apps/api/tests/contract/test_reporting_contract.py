"""Contract coverage for the R2.5 reporting surface — task T010, against T007's contract
(specs/012-reporting-hardening/contracts/reporting-hardening.openapi.yaml).

Wave 16 scope: the schedules CRUD, the artifacts list, the extended on-demand exports, and
the (already-landed) download endpoint. The digest endpoints and the reporting_timezone
field on PATCH /tenant are Wave 17 surfaces (T024, T018); their contract tests are added by
those lanes into this file, the same way every prior chunk accumulated coverage here.

The reports schemas and routes do not exist yet (T011/T012) — their imports are deferred
into the test bodies so they are red for the right reason and drive the implementation. The
exports schemas DO exist: the extension tests (T014) assert the target contract directly —
kinds, csv, the branch filter, the kind/format matrix — so they fail against today's
narrower surface and go green as the lane lands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.main import API_PREFIX, create_app
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters, ExportJob


def _schedules_schemas() -> tuple[type, type, type]:
    """Deferred import — red for the right reason until T011 lands the module."""
    from procurepilot_api.modules.reports.schemas import (
        ReportSchedule,
        ReportScheduleCreate,
        ReportScheduleUpdate,
    )

    return ReportSchedule, ReportScheduleCreate, ReportScheduleUpdate


def _artifacts_schema() -> type:
    from procurepilot_api.modules.reports.schemas import ReportArtifact

    return ReportArtifact


# --- schedules CRUD shapes (T011/T012) ---------------------------------------


def test_schedule_create_shape_rejects_tenant_id_and_accepts_the_contract_fields() -> None:
    _, ReportScheduleCreate, _ = _schedules_schemas()
    payload = {
        "kind": "savings_ledger",
        "format": "xlsx",
        "filters": {"supplier_id": None, "branch_id": None},
        "weekday": 0,
        "locale": "ar",
        "tenant_id": str(uuid4()),
    }
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate(payload)

    del payload["tenant_id"]
    request = ReportScheduleCreate.model_validate(payload)
    assert request.kind == "savings_ledger"
    assert request.format == "xlsx"
    assert request.weekday == 0
    assert request.locale == "ar"


def test_schedule_create_rejects_out_of_range_weekday_and_unknown_locale() -> None:
    _, ReportScheduleCreate, _ = _schedules_schemas()
    base = {"kind": "savings_ledger", "format": "xlsx", "weekday": 0}
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate({**base, "weekday": 7})
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate({**base, "weekday": -1})
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate({**base, "locale": "fr"})


def test_schedule_create_rejects_an_unknown_kind_or_format() -> None:
    _, ReportScheduleCreate, _ = _schedules_schemas()
    base = {"format": "xlsx", "weekday": 0}
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate({**base, "kind": "vendor_of_record"})
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate(
            {"kind": "savings_ledger", "weekday": 0, "format": "docx"}
        )


def test_schedule_create_refuses_pdf_for_spend_by_supplier() -> None:
    """The kind/format matrix (FR-002) is enforced at the boundary: PDF is not offered for
    spend_by_supplier, whose value is the currency-grouped table, not a printable layout."""
    _, ReportScheduleCreate, _ = _schedules_schemas()
    with pytest.raises(ValidationError):
        ReportScheduleCreate.model_validate(
            {"kind": "spend_by_supplier", "format": "pdf", "weekday": 0}
        )
    # CSV and XLSX are valid for every kind.
    for fmt in ("csv", "xlsx"):
        request = ReportScheduleCreate.model_validate(
            {"kind": "spend_by_supplier", "format": fmt, "weekday": 3}
        )
        assert request.format == fmt


def test_schedule_update_shape_allows_pause_and_resume_only_between_two_states() -> None:
    _, _, ReportScheduleUpdate = _schedules_schemas()
    paused = ReportScheduleUpdate.model_validate({"status": "paused"})
    resumed = ReportScheduleUpdate.model_validate({"status": "active"})
    assert paused.status == "paused"
    assert resumed.status == "active"
    with pytest.raises(ValidationError):
        ReportScheduleUpdate.model_validate({"status": "cancelled"})


def test_schedule_response_shape_carries_the_contract_fields() -> None:
    ReportSchedule, _, _ = _schedules_schemas()
    schedule = ReportSchedule(
        id=uuid4(),
        kind="savings_ledger",
        format="xlsx",
        filters={"supplier_id": None, "branch_id": None},
        weekday=0,
        status="active",
        next_run_at=datetime.now(UTC),
        last_run_at=None,
        rule_version="",
        locale="en",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    body = schedule.model_dump(mode="json")
    for field in (
        "id",
        "kind",
        "format",
        "filters",
        "weekday",
        "status",
        "next_run_at",
        "last_run_at",
        "rule_version",
        "locale",
        "created_at",
        "updated_at",
    ):
        assert field in body, f"the contract requires {field} on ReportSchedule"


# --- artifacts list shape (T012) ---------------------------------------------


def test_artifact_shape_carries_the_contract_fields() -> None:
    ReportArtifact = _artifacts_schema()
    artifact = ReportArtifact(
        id=uuid4(),
        kind="spend_by_supplier",
        format="csv",
        filters={
            "period_start": "2026-09-07",
            "period_end": "2026-09-13",
            "supplier_id": None,
            "branch_id": None,
        },
        status="completed",
        row_count=4,
        rule_version="landed-cost-v1",
        schedule_id=None,
        locale="en",
        download_url="/api/v1/exports/x/download",
        expires_at=None,
        error=None,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    body = artifact.model_dump(mode="json")
    for field in (
        "id",
        "kind",
        "format",
        "filters",
        "status",
        "row_count",
        "rule_version",
        "schedule_id",
        "locale",
        "download_url",
        "expires_at",
        "error",
        "created_at",
        "started_at",
        "completed_at",
    ):
        assert field in body, f"the contract requires {field} on ReportArtifact"


def test_artifact_status_includes_the_purged_expired_state() -> None:
    ReportArtifact = _artifacts_schema()
    artifact = ReportArtifact(
        id=uuid4(),
        kind="savings_ledger",
        format="xlsx",
        filters={"period_start": "2026-09-07"},
        status="expired",
        row_count=4,
        rule_version="",
        locale="en",
        created_at=datetime.now(UTC),
    )
    assert artifact.model_dump(mode="json")["status"] == "expired"


# --- routes (T012 wiring; download already landed) ---------------------------


def test_reporting_routes_are_registered() -> None:
    from procurepilot_api.main import create_app as build

    app = build()
    paths = {route.path for route in app.routes}
    expected = {
        f"{API_PREFIX}/reports/schedules",
        f"{API_PREFIX}/reports/schedules/{{schedule_id}}",
        f"{API_PREFIX}/reports/artifacts",
    }
    assert expected <= paths, (
        f"missing reporting routes: {expected - paths} — is the reports router wired "
        f"into main.py (T012)?"
    )


def test_download_route_is_registered() -> None:
    """Landed with the Wave 15 remediation — pinned here so drift cannot remove it."""
    app = create_app()
    paths = {route.path for route in app.routes}
    assert f"{API_PREFIX}/exports/{{id}}/download" in paths


# --- extended on-demand exports (T014) ---------------------------------------


def test_export_create_accepts_every_wave16_kind_and_the_branch_filter() -> None:
    for kind in ("savings_ledger", "spend_by_supplier", "alerts_summary"):
        request = ExportCreate.model_validate(
            {
                "kind": kind,
                "format": "csv",
                "filters": {
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                    "branch_id": str(uuid4()),
                },
            }
        )
        assert request.kind == kind
        assert request.format == "csv"
        assert request.filters.branch_id is not None


def test_export_create_refuses_pdf_for_spend_by_supplier() -> None:
    with pytest.raises(ValidationError):
        ExportCreate.model_validate(
            {
                "kind": "spend_by_supplier",
                "format": "pdf",
                "filters": {"period_start": "2026-08-01"},
            }
        )


def test_export_filters_still_reject_inverted_periods() -> None:
    """The R2.4 period guard stays while the surface widens (honest window, not new sloppiness)."""
    with pytest.raises(ValidationError):
        ExportFilters(period_start="2026-08-31", period_end="2026-08-01")


def test_export_job_shape_records_locale_for_artifact_language() -> None:
    """FR-029: the locale rides the job so members can identify an artifact's language
    before download."""
    job = ExportJob(
        id=uuid4(),
        kind="spend_by_supplier",
        format="csv",
        filters=ExportFilters(period_start="2026-08-01", period_end="2026-08-31"),
        status="queued",
        locale="ar",
        created_at=datetime.now(UTC),
    )
    assert job.model_dump(mode="json")["locale"] == "ar"
