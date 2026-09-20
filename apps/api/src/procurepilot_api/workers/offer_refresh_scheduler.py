"""Schedule connector-neutral refresh work for active supplier offers (R3.4).

This worker only maintains refresh intent. A later connector worker owns provider calls and
ingestion; no purchase, quotation, or landed-cost row is changed here.
"""

from __future__ import annotations

import argparse
import logging
import time

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings

logger = logging.getLogger(__name__)


def tick(settings: Settings) -> dict[str, int]:
    stats = {"observed": 0, "due": 0, "enqueued": 0}
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("set local role service_role")
            cur.execute(
                """
                with ranked as (
                  select
                    md.tenant_id,
                    md.matched_workspace_product_id as workspace_product_id,
                    q.supplier_id,
                    lc.recorded_at,
                    latest_import.id as source_import_id,
                    row_number() over (
                      partition by md.tenant_id, md.matched_workspace_product_id, q.supplier_id
                      order by lc.recorded_at desc, lc.id desc
                    ) as rn
                  from match_decision md
                  join landed_cost lc on lc.match_decision_id = md.id
                  join quotation_line ql on ql.id = lc.quotation_line_id
                  join quotation q on q.id = ql.quotation_id
                  join workspace_product wp
                    on wp.tenant_id = md.tenant_id
                   and wp.id = md.matched_workspace_product_id
                  join supplier s
                    on s.tenant_id = md.tenant_id
                   and s.id = q.supplier_id
                  left join lateral (
                    select ci.id
                    from catalogue_imports ci
                    where ci.tenant_id = md.tenant_id
                      and ci.supplier_id = q.supplier_id
                      and ci.status = 'completed'
                    order by ci.created_at desc, ci.id desc
                    limit 1
                  ) latest_import on true
                  where wp.status = 'active'
                    and q.status = 'reviewed'
                    and s.status in ('active', 'preferred')
                )
                insert into offer_refresh_schedule
                  (tenant_id, workspace_product_id, supplier_id, next_refresh_at,
                   last_observed_at, source_import_id)
                select tenant_id, workspace_product_id, supplier_id,
                       recorded_at + make_interval(days => %s), recorded_at, source_import_id
                from ranked
                where rn = 1
                on conflict (tenant_id, workspace_product_id, supplier_id)
                do update set
                  last_observed_at = excluded.last_observed_at,
                  source_import_id = coalesce(
                    excluded.source_import_id, offer_refresh_schedule.source_import_id
                  ),
                  next_refresh_at = case
                    when offer_refresh_schedule.last_observed_at is distinct from
                         excluded.last_observed_at
                    then excluded.last_observed_at
                         + make_interval(days => offer_refresh_schedule.cadence_days)
                    else offer_refresh_schedule.next_refresh_at
                  end,
                  status = case
                    when offer_refresh_schedule.status = 'due'
                     and excluded.last_observed_at > offer_refresh_schedule.last_observed_at
                    then 'active'
                    else offer_refresh_schedule.status
                  end,
                  updated_at = now()
                """,
                (settings.offer_freshness_target_days,),
            )
            stats["observed"] = cur.rowcount
            cur.execute(
                """
                update offer_refresh_schedule
                set status = 'due', last_requested_at = now(), updated_at = now()
                where status = 'active'
                  and next_refresh_at <= now()
                  and source_import_id is not null
                returning id, tenant_id, workspace_product_id, supplier_id, source_import_id
                """
            )
            due_rows = [dict(row) for row in cur.fetchall()]
            stats["due"] = len(due_rows)
            for row in due_rows:
                cur.execute(
                    """
                    insert into ingestion_jobs (tenant_id, job_type, payload)
                    values (%s, 'catalogue_import', %s)
                    """,
                    (
                        row["tenant_id"],
                        Jsonb(
                            {
                                "refresh_schedule_id": str(row["id"]),
                                "workspace_product_id": str(row["workspace_product_id"]),
                                "supplier_id": str(row["supplier_id"]),
                                "source_import_id": str(row["source_import_id"]),
                            }
                        ),
                    ),
                )
                stats["enqueued"] += 1
        conn.commit()
    return stats


def run_loop(settings: Settings, *, once: bool = False, interval_seconds: int = 3600) -> None:
    logger.info("Starting offer refresh scheduler (once=%s, interval=%ss)", once, interval_seconds)
    while True:
        try:
            stats = tick(settings)
            if stats["observed"] or stats["due"] or stats["enqueued"]:
                logger.info("Offer refresh scheduling pass completed: %s", stats)
        except Exception:
            logger.exception("Error during offer refresh scheduling pass")
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offer freshness and refresh scheduler")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    args = parser.parse_args()
    run_loop(get_settings(), once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
