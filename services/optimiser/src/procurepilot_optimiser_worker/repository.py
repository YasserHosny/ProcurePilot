from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_optimiser_worker.models import BasketJob, Money, OfferInput


def load_job(conn: psycopg.Connection, *, job_id: UUID, tenant_id: UUID) -> BasketJob:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, supplier_ids, items
            from basket_split_job
            where id = %s and tenant_id = %s
            """,
            (job_id, tenant_id),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("basket split job not found")
    return BasketJob.model_validate(dict(row))


def read_current_offers(conn: psycopg.Connection, *, job: BasketJob) -> list[OfferInput]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            with requested as (
              select *
              from jsonb_to_recordset(%s::jsonb)
                as item(workspace_product_id uuid, quantity numeric)
            ),
            ranked as (
              select
                lc.id as offer_id,
                md.matched_workspace_product_id as workspace_product_id,
                q.supplier_id,
                req.quantity as requested_quantity,
                lc.total_currency,
                -- req.quantity is denominated in the product's normalised base unit (matching
                -- offers/compare in apps/api), never the supplier's original pack/case count, so
                -- project from normalised_base_quantity rather than the raw pack quantity.
                (lc.total_amount / lc.normalised_base_quantity * req.quantity) as projected_total,
                row_number() over (
                  partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
                  order by lc.recorded_at desc, lc.id desc
                ) as rn
              from requested req
              join match_decision md on md.matched_workspace_product_id = req.workspace_product_id
              join landed_cost lc on lc.match_decision_id = md.id
              join quotation_line ql on ql.id = lc.quotation_line_id
              join quotation q on q.id = ql.quotation_id
              join supplier s on s.id = q.supplier_id
              where lc.tenant_id = %s
                and q.supplier_id = any(%s::uuid[])
                and q.status = 'reviewed'
                and s.status in ('active', 'preferred')
                and (lc.valid_to is null or lc.valid_to >= now())
            )
            select * from ranked where rn = 1
            """,
            (
                Jsonb([item.model_dump(mode="json") for item in job.items]),
                job.tenant_id,
                [str(supplier_id) for supplier_id in job.supplier_ids],
            ),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return [_offer(row) for row in rows]


def mark_running(conn: psycopg.Connection, *, job_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update basket_split_job set status = 'running', started_at = now() where id = %s",
            (job_id,),
        )


def mark_completed(conn: psycopg.Connection, *, job_id: UUID, result: object) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update basket_split_job
            set status = 'completed', result = %s, completed_at = now()
            where id = %s
            """,
            (Jsonb(result), job_id),
        )


def mark_failed(conn: psycopg.Connection, *, job_id: UUID, error: dict[str, object]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update basket_split_job
            set status = 'failed', error = %s, completed_at = now()
            where id = %s
            """,
            (Jsonb(error), job_id),
        )


def _offer(row: dict[str, object]) -> OfferInput:
    amount = Decimal(str(row["projected_total"])).quantize(Decimal("0.0001"))
    return OfferInput(
        offer_id=UUID(str(row["offer_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        quantity=format(Decimal(str(row["requested_quantity"])).quantize(Decimal("0.000001")), "f"),
        total_landed_cost=Money(amount=format(amount, "f"), currency=str(row["total_currency"])),
    )
