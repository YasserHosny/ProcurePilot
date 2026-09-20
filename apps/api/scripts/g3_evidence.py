"""Report the current hosted-data baseline for the Phase 3 G3 gate.

This is intentionally read-only. It measures tenant-scoped records without creating or changing
customer data, so it can be rerun after each integration release.
"""

from __future__ import annotations

import json
import os
from datetime import date
from uuid import UUID

import psycopg


def main() -> None:
    excluded_tenant_ids = _parse_excluded_tenant_ids(
        os.getenv("G3_EXCLUDED_TENANT_IDS")
    )
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        active_account_query, active_account_params = _active_accounts_query(excluded_tenant_ids)
        active_accounts = _scalar(
            conn,
            active_account_query,
            active_account_params,
        )
        quotation_filter, quotation_params = _tenant_filter("q.tenant_id", excluded_tenant_ids)
        integration_sourced_quotations, active_quotations = conn.execute(
            f"""
            select
              count(*) filter (where d.source_channel <> 'upload'),
              count(*)
            from quotation q
            join document d on d.id = q.document_id and d.tenant_id = q.tenant_id
            where q.deleted_at is null{quotation_filter}
            """,
            quotation_params,
        ).fetchone()
        history_filter, history_params = _tenant_filter("tenant_id", excluded_tenant_ids)
        history_accounts = _scalar(
            conn,
            f"""
            select count(*)
            from (
              select tenant_id
              from purchase_order
              where true{history_filter}
              group by tenant_id
              having max(order_date) - min(order_date) >= 180
            ) accounts
            """,
            history_params,
        )
        history_start, history_end = conn.execute(
            f"select min(order_date), max(order_date) from purchase_order "
            f"where true{history_filter}",
            history_params,
        ).fetchone()
        schedule_filter, schedule_params = _tenant_filter("tenant_id", excluded_tenant_ids)
        active_schedules, linked_schedules = conn.execute(
            f"""
            select
              count(*) filter (where status = 'active'),
              count(*) filter (where status = 'active' and source_import_id is not null)
            from offer_refresh_schedule
            where true{schedule_filter}
            """,
            schedule_params,
        ).fetchone()
        review_filter, review_params = _tenant_filter("tenant_id", excluded_tenant_ids)
        pending_refresh_reviews = _scalar(
            conn,
            f"select count(*) from catalogue_refresh_review "
            f"where status = 'pending_review'{review_filter}",
            review_params,
        )

    print(
        json.dumps(
            {
                "measured_at": date.today().isoformat(),
                "excluded_tenant_ids": list(excluded_tenant_ids),
                "active_accounts": active_accounts,
                "active_quotations": active_quotations,
                "integration_sourced_quotations": integration_sourced_quotations,
                "integration_sourced_share": (
                    integration_sourced_quotations / active_quotations
                    if active_quotations
                    else 0
                ),
                "accounts_with_180_day_purchase_history": history_accounts,
                "purchase_history_start": history_start.isoformat() if history_start else None,
                "purchase_history_end": history_end.isoformat() if history_end else None,
                "active_refresh_schedules": int(active_schedules or 0),
                "refresh_schedules_with_sources": int(linked_schedules or 0),
                "pending_refresh_reviews": pending_refresh_reviews,
            },
            indent=2,
        )
    )


def _parse_excluded_tenant_ids(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    try:
        parsed = {str(UUID(value.strip())) for value in raw.split(",") if value.strip()}
    except ValueError as exc:
        raise ValueError("G3_EXCLUDED_TENANT_IDS must be a comma-separated UUID list") from exc
    return tuple(sorted(parsed))


def _active_accounts_query(
    excluded_tenant_ids: tuple[str, ...],
) -> tuple[str, tuple[object, ...]]:
    tenant_filter, tenant_params = _tenant_filter("m.tenant_id", excluded_tenant_ids)
    return (
        "select count(distinct m.tenant_id) "
        "from membership m join tenant t on t.id = m.tenant_id "
        f"where m.status = 'active'{tenant_filter}",
        tenant_params,
    )


def _tenant_filter(
    column: str,
    excluded_tenant_ids: tuple[str, ...],
) -> tuple[str, tuple[object, ...]]:
    if not excluded_tenant_ids:
        return "", ()
    return f" and not ({column} = any(%s::uuid[]))", (list(excluded_tenant_ids),)


def _scalar(
    conn: psycopg.Connection,
    query: str,
    params: tuple[object, ...] = (),
) -> int:
    return int(conn.execute(query, params).fetchone()[0])


if __name__ == "__main__":
    main()
