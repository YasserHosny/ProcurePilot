from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.digests.service import _tenant_context
from procurepilot_api.modules.ingestion.schemas import IngestionStats
from procurepilot_api.modules.offers.service import _authenticated_db


def derive_calendar_windows(
    tz_name: str, *, now: datetime | None = None
) -> tuple[datetime, datetime, datetime]:
    """Compute (today_start, week_start, month_start) in timezone tz_name.

    - today_start: 00:00:00 local time today.
    - week_start: 00:00:00 local time on Monday of the current week (ISO weekday 0).
    - month_start: 00:00:00 local time on the 1st of the current month.
    """
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    reference_now = now or datetime.now(UTC)
    local_dt = reference_now.astimezone(tz)
    local_date = local_dt.date()

    today_start = datetime.combine(local_date, time.min, tzinfo=tz)
    week_start = datetime.combine(
        local_date - timedelta(days=local_date.weekday()), time.min, tzinfo=tz
    )
    month_start = datetime.combine(local_date.replace(day=1), time.min, tzinfo=tz)

    return today_start, week_start, month_start


def get_ingestion_stats(
    *,
    member: CurrentMember,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> IngestionStats:
    """T021 — Ingestion dashboard stats aggregate object.

    Computes:
    - emails_received_today / _week / _month: ingestion_email_log rows within tenant-local
      calendar boundaries in the tenant's reporting_timezone.
    - capture_uploads_total: all-time quotations with source = 'capture'.
    - catalogue_imports_total: all-time catalogue imports for the tenant.
    - supplier_match_rate: fraction of completed ingestion_email_log rows that have a matched
      supplier (supplier_id is not null).
    - extraction_success_rate: fraction of completed extraction jobs for ingestion quotations
      (source in ('email', 'capture')) with status = 'succeeded'.
    """
    resolved_settings = settings or get_settings()

    with _authenticated_db(resolved_settings, member) as conn:
        ctx = _tenant_context(conn, member.tenant_id, member.membership_id)
        tz_name = str(ctx.get("reporting_timezone") or "UTC")
        today_start, week_start, month_start = derive_calendar_windows(tz_name, now=now)

        with conn.cursor(row_factory=dict_row) as cur:
            # 1. Email counts & supplier match counts from ingestion_email_log
            cur.execute(
                """
                select
                    count(*) filter (where received_at >= %(today_start)s)
                        as emails_received_today,
                    count(*) filter (where received_at >= %(week_start)s)
                        as emails_received_week,
                    count(*) filter (where received_at >= %(month_start)s)
                        as emails_received_month,
                    count(*) filter (where status = 'completed')
                        as emails_completed,
                    count(*) filter (where status = 'completed' and supplier_id is not null)
                        as emails_matched
                from ingestion_email_log
                where tenant_id = %(tenant_id)s
                """,
                {
                    "tenant_id": member.tenant_id,
                    "today_start": today_start,
                    "week_start": week_start,
                    "month_start": month_start,
                },
            )
            email_row = cur.fetchone() or {}

            # 2. Capture uploads total (all-time quotation rows where source = 'capture')
            cur.execute(
                """
                select count(*) as capture_uploads_total
                from quotation
                where tenant_id = %(tenant_id)s
                  and source = 'capture'
                """,
                {"tenant_id": member.tenant_id},
            )
            capture_row = cur.fetchone() or {}

            # 3. Catalogue imports total (all-time catalogue_imports rows for the tenant)
            cur.execute(
                """
                select count(*) as catalogue_imports_total
                from catalogue_imports
                where tenant_id = %(tenant_id)s
                """,
                {"tenant_id": member.tenant_id},
            )
            catalogue_row = cur.fetchone() or {}

            # 4. Extraction success components for ingestion-sourced quotations
            # Scoped to quotation.source in ('email', 'capture').
            # Denominator: jobs leaving 'queued'/'running' (status 'succeeded' or 'failed').
            # Numerator: jobs with status = 'succeeded'.
            cur.execute(
                """
                select
                    count(*) filter (where ej.status not in ('queued', 'running'))
                        as total_terminal,
                    count(*) filter (where ej.status = 'succeeded')
                        as total_succeeded
                from extraction_job ej
                join quotation q on q.id = ej.quotation_id and q.tenant_id = ej.tenant_id
                where ej.tenant_id = %(tenant_id)s
                  and q.source in ('email', 'capture')
                """,
                {"tenant_id": member.tenant_id},
            )
            extraction_row = cur.fetchone() or {}

    emails_received_today = int(email_row.get("emails_received_today") or 0)
    emails_received_week = int(email_row.get("emails_received_week") or 0)
    emails_received_month = int(email_row.get("emails_received_month") or 0)
    emails_completed = int(email_row.get("emails_completed") or 0)
    emails_matched = int(email_row.get("emails_matched") or 0)

    capture_uploads_total = int(capture_row.get("capture_uploads_total") or 0)
    catalogue_imports_total = int(catalogue_row.get("catalogue_imports_total") or 0)

    total_terminal = int(extraction_row.get("total_terminal") or 0)
    total_succeeded = int(extraction_row.get("total_succeeded") or 0)

    # Denominator for supplier_match_rate:
    # Scoped to ingestion_email_log rows with status = 'completed' (processed emails).
    # Incomplete, failed, rejected, or duplicate emails are excluded from the denominator
    # because supplier matching was either never attempted or aborted due to early failure;
    # including them would penalize match rate for delivery/format failures.
    # 0/0 handling: Resolves to 0.0 per parallel-execution-plan-ingestion-wave4.md §2 T021.
    supplier_match_rate = (
        float(emails_matched) / float(emails_completed) if emails_completed > 0 else 0.0
    )

    # Denominator for extraction_success_rate:
    # Scoped strictly to extraction_job rows belonging to ingestion-sourced quotations
    # (quotation.source in ('email', 'capture')) that have completed processing
    # (status not in ('queued', 'running'), i.e. status is 'succeeded' or 'failed').
    # Excludes non-ingestion quotations (manual upload) to accurately reflect automated
    # ingestion extraction quality, and excludes in-flight jobs.
    # 0/0 handling: Resolves to 0.0 per parallel-execution-plan-ingestion-wave4.md §2 T021.
    extraction_success_rate = (
        float(total_succeeded) / float(total_terminal) if total_terminal > 0 else 0.0
    )

    return IngestionStats(
        emails_received_today=emails_received_today,
        emails_received_week=emails_received_week,
        emails_received_month=emails_received_month,
        capture_uploads_total=capture_uploads_total,
        catalogue_imports_total=catalogue_imports_total,
        supplier_match_rate=supplier_match_rate,
        extraction_success_rate=extraction_success_rate,
    )
