from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.modules.offers.price_history import normalised_unit_price

LATEST_LANDED_COST_SQL = """
select
  lc.id as landed_cost_id,
  lc.total_amount,
  lc.total_currency,
  lc.normalised_base_quantity
from workspace_product wp
join match_decision md on md.matched_workspace_product_id = wp.id
join landed_cost lc on lc.match_decision_id = md.id
where wp.id = %(workspace_product_id)s
order by lc.recorded_at desc, lc.id desc
limit 1
"""


@dataclass(frozen=True)
class LineEstimate:
    """A purchase-request line's estimated value, reusing the exact price-history mechanism
    offers/price_history.py already uses for last_paid (research.md R2). All three fields are
    null together when the product has no reachable landed_cost row — an "incomplete estimate",
    never a silent zero."""

    unit_price_amount: Decimal | None
    unit_price_currency: str | None
    source_landed_cost_id: UUID | None


def estimate_line_value(
    conn: psycopg.Connection, *, workspace_product_id: UUID
) -> LineEstimate:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(LATEST_LANDED_COST_SQL, {"workspace_product_id": workspace_product_id})
        row = cur.fetchone()

    if row is None:
        return LineEstimate(
            unit_price_amount=None, unit_price_currency=None, source_landed_cost_id=None
        )

    amount = normalised_unit_price(row["total_amount"], row["normalised_base_quantity"])
    return LineEstimate(
        unit_price_amount=amount,
        unit_price_currency=str(row["total_currency"]),
        source_landed_cost_id=row["landed_cost_id"],
    )
