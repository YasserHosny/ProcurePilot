from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
)
from integration.quotation_helpers import (
    ensure_quotation_reference_data,
    make_document,
    make_supplier,
)
from integration.smart_compare_helpers import member_from_workspace, settings_for_test_db
from procurepilot_api.deps import current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.ingestion.stats_service import (
    derive_calendar_windows,
    get_ingestion_stats,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    return app


def _seed_email(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    message_id: str,
    received_at: datetime,
    status: str = "completed",
    supplier_id: UUID | None = None,
    match_method: str | None = None,
    quotation_id: UUID | None = None,
) -> UUID:
    email_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        """
        insert into ingestion_email_log
          (id, tenant_id, message_id, from_address, from_domain, subject,
           received_at, status, supplier_id, match_method, quotation_id)
        values
          (%s, %s, %s, 'vendor@test.com', 'test.com', 'Quote',
           %s, %s::ingestion_email_status, %s, %s, %s)
        """,
        (
            email_id,
            workspace.tenant_id,
            message_id,
            received_at,
            status,
            supplier_id,
            match_method,
            quotation_id,
        ),
    )
    return email_id


def _seed_quotation(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    source: str = "capture",
    supplier_id: UUID | None = None,
) -> UUID:
    quotation_id = uuid4()
    document_id = make_document(cur, workspace)
    act_as(cur, workspace)
    cur.execute(
        """
        insert into quotation
          (id, tenant_id, document_id, supplier_id, status, currency, source)
        values
          (%s, %s, %s, %s, 'pending', 'GBP', %s)
        """,
        (quotation_id, workspace.tenant_id, document_id, supplier_id, source),
    )
    return quotation_id


def _seed_catalogue_import(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    supplier_id: UUID,
    status: str = "completed",
) -> UUID:
    import_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        """
        insert into catalogue_imports
          (id, tenant_id, supplier_id, file_name, file_path, file_size_bytes,
           file_format, status, created_by)
        values
          (%s, %s, %s, 'price-list.csv', 'tenants/test/price-list.csv', 1024,
           'csv', %s::catalogue_import_status, %s)
        """,
        (import_id, workspace.tenant_id, supplier_id, status, workspace.membership_id),
    )
    return import_id


def _seed_extraction_job(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    quotation_id: UUID,
    status: str = "succeeded",
    completed_at: datetime | None = None,
) -> UUID:
    job_id = uuid4()
    act_as(cur, workspace)
    # Check constraint: completed_at must be non-null iff status in ('succeeded', 'failed')
    if status in ("succeeded", "failed") and completed_at is None:
        completed_at = datetime.now(UTC)
    elif status in ("queued", "running"):
        completed_at = None

    cur.execute(
        """
        insert into extraction_job
          (id, tenant_id, quotation_id, status, completed_at)
        values
          (%s, %s, %s, %s::extraction_job_status, %s)
        """,
        (job_id, workspace.tenant_id, quotation_id, status, completed_at),
    )
    return job_id


def test_zero_activity_tenant_returns_all_zero_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tenant with no activity returns all zero counts and 0.0 rates with no division-by-zero."""
    settings = settings_for_test_db(monkeypatch)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, "stats-zero")
            conn.commit()

    member = member_from_workspace(workspace)
    stats = get_ingestion_stats(member=member, settings=settings)

    # All counts must be exactly 0
    assert stats.emails_received_today == 0
    assert stats.emails_received_week == 0
    assert stats.emails_received_month == 0
    assert stats.capture_uploads_total == 0
    assert stats.catalogue_imports_total == 0

    # Explicit assertion: 0/0 rate resolves to 0.0 float per plan doc §2 T021
    assert stats.supplier_match_rate == 0.0
    assert isinstance(stats.supplier_match_rate, float)
    assert stats.extraction_success_rate == 0.0
    assert isinstance(stats.extraction_success_rate, float)


def test_realistic_mix_computes_exact_rates_by_hand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tenant with a realistic mix produces exactly hand-calculated rates:

    Reference time: 2026-09-17 12:00:00 UTC (Thursday)
    - today_start:  2026-09-17 00:00:00 UTC
    - week_start:   2026-09-14 00:00:00 UTC (Monday)
    - month_start:  2026-09-01 00:00:00 UTC

    Seeded Ingestion Emails (8 total):
    1. 2026-09-17 10:00 UTC: status=completed, matched (supplier_1) -> today, week, month, matched
    2. 2026-09-17 08:00 UTC: status=completed, unmatched           -> today, week, month, unmatched
    3. 2026-09-17 06:00 UTC: status=processing, unmatched          -> today, week, month, in-flight
    4. 2026-09-15 14:00 UTC: status=completed, matched (supplier_1) -> week, month, matched
    5. 2026-09-05 12:00 UTC: status=completed, matched (supplier_1) -> month, matched
    6. 2026-08-20 12:00 UTC: status=completed, unmatched           -> older, unmatched
    7. 2026-08-15 12:00 UTC: status=rejected, unmatched            -> older, rejected
    8. 2026-08-10 12:00 UTC: status=failed, unmatched              -> older, failed

    Emails counts:
    - emails_received_today = 3 (1, 2, 3)
    - emails_received_week  = 4 (1, 2, 3, 4)
    - emails_received_month = 5 (1, 2, 3, 4, 5)

    Supplier match rate:
    - Denominator: completed rows = 5 (1, 2, 4, 5, 6)
    - Numerator: matched completed rows = 3 (1, 4, 5)
    - Rate = 3 / 5 = 0.60

    Quotations:
    - Q1: source=capture
    - Q2: source=capture
    - Q3: source=capture
    - Q4: source=email
    - Q5: source=upload (manual upload — ignored from ingestion stats)
    - capture_uploads_total = 3 (Q1, Q2, Q3)

    Catalogue imports:
    - Import 1: completed
    - Import 2: failed
    - catalogue_imports_total = 2

    Extraction jobs on ingestion quotations (Q1, Q2, Q3, Q4):
    - J1 (on Q1, capture): status=succeeded -> terminal, succeeded
    - J2 (on Q2, capture): status=failed    -> terminal, failed
    - J3 (on Q3, capture): status=succeeded -> terminal, succeeded
    - J4 (on Q4, email):   status=succeeded -> terminal, succeeded
    - J5 (on Q4, email):   status=running   -> in-flight (excluded from denominator)
    - J6 (on Q5, upload):  status=succeeded -> manual upload (excluded completely)

    Extraction success rate:
    - Denominator: terminal jobs on ingestion quotations = 4 (J1, J2, J3, J4)
    - Numerator: succeeded jobs = 3 (J1, J3, J4)
    - Rate = 3 / 4 = 0.75
    """
    settings = settings_for_test_db(monkeypatch)
    ref_now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, "stats-rates")
            supplier_id = make_supplier(cur, workspace, name="Test Supplier")

            # Seed 8 emails
            _seed_email(
                cur,
                workspace,
                message_id="msg-1",
                received_at=datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC),
                status="completed",
                supplier_id=supplier_id,
                match_method="domain",
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-2",
                received_at=datetime(2026, 9, 17, 8, 0, 0, tzinfo=UTC),
                status="completed",
                supplier_id=None,
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-3",
                received_at=datetime(2026, 9, 17, 6, 0, 0, tzinfo=UTC),
                status="processing",
                supplier_id=None,
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-4",
                received_at=datetime(2026, 9, 15, 14, 0, 0, tzinfo=UTC),
                status="completed",
                supplier_id=supplier_id,
                match_method="address",
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-5",
                received_at=datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC),
                status="completed",
                supplier_id=supplier_id,
                match_method="thread",
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-6",
                received_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC),
                status="completed",
                supplier_id=None,
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-7",
                received_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC),
                status="rejected",
                supplier_id=None,
            )
            _seed_email(
                cur,
                workspace,
                message_id="msg-8",
                received_at=datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC),
                status="failed",
                supplier_id=None,
            )

            # Seed 5 quotations (3 capture, 1 email, 1 upload)
            q1 = _seed_quotation(cur, workspace, source="capture", supplier_id=supplier_id)
            q2 = _seed_quotation(cur, workspace, source="capture", supplier_id=supplier_id)
            q3 = _seed_quotation(cur, workspace, source="capture", supplier_id=supplier_id)
            q4 = _seed_quotation(cur, workspace, source="email", supplier_id=supplier_id)
            q5 = _seed_quotation(cur, workspace, source="upload", supplier_id=supplier_id)

            # Seed 2 catalogue imports
            _seed_catalogue_import(cur, workspace, supplier_id=supplier_id, status="completed")
            _seed_catalogue_import(cur, workspace, supplier_id=supplier_id, status="failed")

            # Seed extraction jobs
            _seed_extraction_job(cur, workspace, quotation_id=q1, status="succeeded")
            _seed_extraction_job(cur, workspace, quotation_id=q2, status="failed")
            _seed_extraction_job(cur, workspace, quotation_id=q3, status="succeeded")
            _seed_extraction_job(cur, workspace, quotation_id=q4, status="succeeded")
            _seed_extraction_job(cur, workspace, quotation_id=q4, status="running")
            _seed_extraction_job(cur, workspace, quotation_id=q5, status="succeeded")

            conn.commit()

    member = member_from_workspace(workspace)
    stats = get_ingestion_stats(member=member, settings=settings, now=ref_now)

    # Hand-calculated assertions
    assert stats.emails_received_today == 3
    assert stats.emails_received_week == 4
    assert stats.emails_received_month == 5
    assert stats.capture_uploads_total == 3
    assert stats.catalogue_imports_total == 2
    assert stats.supplier_match_rate == 0.60
    assert stats.extraction_success_rate == 0.75


def test_cross_tenant_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second tenant's activity never appears in the first tenant's stats."""
    settings = settings_for_test_db(monkeypatch)
    ref_now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            # Tenant A: zero activity
            workspace_a = make_workspace(cur, "stats-iso-a")

            # Tenant B: heavy activity
            workspace_b = make_workspace(cur, "stats-iso-b")
            supplier_b = make_supplier(cur, workspace_b, name="Supplier B")

            for i in range(5):
                _seed_email(
                    cur,
                    workspace_b,
                    message_id=f"msg-b-{i}",
                    received_at=datetime(2026, 9, 17, 10, i, 0, tzinfo=UTC),
                    status="completed",
                    supplier_id=supplier_b,
                    match_method="domain",
                )
            q_b = _seed_quotation(cur, workspace_b, source="capture", supplier_id=supplier_b)
            _seed_catalogue_import(cur, workspace_b, supplier_id=supplier_b, status="completed")
            _seed_extraction_job(cur, workspace_b, quotation_id=q_b, status="succeeded")

            conn.commit()

    member_a = member_from_workspace(workspace_a)
    member_b = member_from_workspace(workspace_b)

    # Tenant A must see zero activity despite Tenant B's rich data
    stats_a = get_ingestion_stats(member=member_a, settings=settings, now=ref_now)
    assert stats_a.emails_received_today == 0
    assert stats_a.emails_received_week == 0
    assert stats_a.emails_received_month == 0
    assert stats_a.capture_uploads_total == 0
    assert stats_a.catalogue_imports_total == 0
    assert stats_a.supplier_match_rate == 0.0
    assert stats_a.extraction_success_rate == 0.0

    # Tenant B sees its own activity
    stats_b = get_ingestion_stats(member=member_b, settings=settings, now=ref_now)
    assert stats_b.emails_received_today == 5
    assert stats_b.capture_uploads_total == 1
    assert stats_b.catalogue_imports_total == 1
    assert stats_b.supplier_match_rate == 1.0
    assert stats_b.extraction_success_rate == 1.0


def test_tenant_timezone_window_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reporting timezone from tenant record correctly drives local calendar boundaries."""
    settings = settings_for_test_db(monkeypatch)

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, "stats-tz")
            # Set reporting timezone to Asia/Riyadh (UTC+3)
            cur.execute(
                "update tenant set reporting_timezone = 'Asia/Riyadh' where id = %s",
                (workspace.tenant_id,),
            )
            # Reference time: 2026-09-17 01:00 UTC -> 04:00 AM in Riyadh (Sept 17)
            # Riyadh today start: 2026-09-17 00:00:00+03:00 = 2026-09-16 21:00:00 UTC
            # An email at 2026-09-16 22:00:00 UTC is received TODAY in Riyadh, but YESTERDAY in UTC.
            _seed_email(
                cur,
                workspace,
                message_id="msg-tz-today",
                received_at=datetime(2026, 9, 16, 22, 0, 0, tzinfo=UTC),
                status="completed",
            )
            # An email at 2026-09-16 20:00:00 UTC is received YESTERDAY in both Riyadh and UTC.
            _seed_email(
                cur,
                workspace,
                message_id="msg-tz-yesterday",
                received_at=datetime(2026, 9, 16, 20, 0, 0, tzinfo=UTC),
                status="completed",
            )
            conn.commit()

    ref_now = datetime(2026, 9, 17, 1, 0, 0, tzinfo=UTC)
    member = member_from_workspace(workspace)
    stats = get_ingestion_stats(member=member, settings=settings, now=ref_now)

    # Only msg-tz-today was received "today" in Asia/Riyadh
    assert stats.emails_received_today == 1


def test_get_stats_http_endpoint_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/ingestion/stats returns 200 and matches IngestionStats schema."""
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, "stats-http")
            conn.commit()

    member = member_from_workspace(workspace)
    client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

    res = client.get("/api/v1/ingestion/stats")
    assert res.status_code == 200, res.text

    data = res.json()
    assert "emails_received_today" in data
    assert "emails_received_week" in data
    assert "emails_received_month" in data
    assert "capture_uploads_total" in data
    assert "catalogue_imports_total" in data
    assert "supplier_match_rate" in data
    assert "extraction_success_rate" in data
    assert "active_refresh_schedule_count" in data
    assert "linked_refresh_schedule_count" in data
    assert "refresh_pilot_ready" in data
    assert data["supplier_match_rate"] == 0.0
    assert data["extraction_success_rate"] == 0.0


def test_derive_calendar_windows_iso_week_and_month_boundaries() -> None:
    """Unit validation for derive_calendar_windows boundary logic."""
    ref = datetime(2026, 9, 17, 15, 30, 0, tzinfo=UTC)  # Thursday
    today_start, week_start, month_start = derive_calendar_windows("UTC", now=ref)

    assert today_start == datetime(2026, 9, 17, 0, 0, 0, tzinfo=UTC)
    assert week_start == datetime(2026, 9, 14, 0, 0, 0, tzinfo=UTC)  # Monday
    assert month_start == datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
