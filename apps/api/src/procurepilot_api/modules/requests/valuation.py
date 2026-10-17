from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.modules.offers.price_history import normalised_unit_price

# Pricing model (see docs/architecture/adrs.md, ADR-020): request/RFQ/PO quantities are in the
# product's PURCHASING unit (a pack: a tin, sack, carton, or a kg for loose goods), so every
# estimate is a price PER PACK. `landed_cost.quantity` is the quoted quantity in packs, so
# total / quantity is the per-pack landed price. Per-base-unit prices (total /
# normalised_base_quantity) are for cross-supplier comparison only and must never be multiplied
# by a pack quantity.
SOURCE_RESPONSE_QUOTE_LINES_SQL = """
select ql.unit_price_amount, ql.unit_price_currency, md.matched_workspace_product_id,
       lc.id as landed_cost_id, lc.total_amount, lc.total_currency, lc.quantity
from rfq_response resp
join quotation_line ql on ql.quotation_id = resp.quotation_id
join match_decision md on md.quotation_line_id = ql.id
left join lateral (
  select id, total_amount, total_currency, quantity
  from landed_cost
  where match_decision_id = md.id
  order by recorded_at desc, id desc
  limit 1
) lc on true
where resp.id = %(rfq_response_id)s
  and md.matched_workspace_product_id = any(%(product_ids)s)
  and ql.unit_price_amount is not null
order by ql.line_number
"""

LATEST_LANDED_COST_SQL = """
select
  lc.id as landed_cost_id,
  lc.total_amount,
  lc.total_currency,
  lc.quantity
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


def estimate_line_value(conn: psycopg.Connection, *, workspace_product_id: UUID) -> LineEstimate:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(LATEST_LANDED_COST_SQL, {"workspace_product_id": workspace_product_id})
        row = cur.fetchone()

    if row is None:
        return LineEstimate(
            unit_price_amount=None, unit_price_currency=None, source_landed_cost_id=None
        )

    amount = normalised_unit_price(row["total_amount"], row["quantity"])
    return LineEstimate(
        unit_price_amount=amount,
        unit_price_currency=str(row["total_currency"]),
        source_landed_cost_id=row["landed_cost_id"],
    )


def estimate_from_source_response(
    conn: psycopg.Connection,
    *,
    rfq_response_id: UUID,
    product_ids: list[UUID],
) -> dict[UUID, LineEstimate]:
    """Per-pack landed prices (falling back to the quoted price) of the RFQ response a request
    was prepared from. A request prepared from a response is valued at that response's prices,
    never at another supplier's (the estimate must not silently change between prepare and
    submit)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            SOURCE_RESPONSE_QUOTE_LINES_SQL,
            {"rfq_response_id": rfq_response_id, "product_ids": product_ids},
        )
        rows = cur.fetchall()
    estimates: dict[UUID, LineEstimate] = {}
    for row in rows:
        landed_quantity = row["quantity"]
        if row["landed_cost_id"] is not None and landed_quantity and landed_quantity > 0:
            # Landed cost carries VAT, delivery and discounts: approval thresholds and budgets
            # must see what the purchase really costs, not the bare line price.
            estimates[row["matched_workspace_product_id"]] = LineEstimate(
                unit_price_amount=normalised_unit_price(row["total_amount"], landed_quantity),
                unit_price_currency=str(row["total_currency"]),
                source_landed_cost_id=row["landed_cost_id"],
            )
        elif row["unit_price_currency"] is not None:
            estimates[row["matched_workspace_product_id"]] = LineEstimate(
                unit_price_amount=Decimal(str(row["unit_price_amount"])),
                unit_price_currency=str(row["unit_price_currency"]),
                source_landed_cost_id=None,
            )
    return estimates
