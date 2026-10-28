"""What an RFQ asked for, read from one of its replies (spec 023 research R2).

The matching module uses this interface rather than querying RFQ tables itself (Constitution VI).
Reads run as the member, so RLS keeps them inside the caller's tenant: another tenant's quotation
or RFQ reads as "no RFQ", never as an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember

RFQ_LINES_FOR_QUOTATION_SQL = """
select rec.rfq_id,
       rl.id as rfq_line_id,
       rl.position,
       rl.workspace_product_id,
       rl.quantity,
       wp.tenant_name as product_name,
       cp.base_unit,
       pack.base_quantity as pack_base_quantity,
       coalesce(
         (select array_agg(pa.alias_text order by pa.created_at, pa.id)
            from product_alias pa
           where pa.tenant_id = rl.tenant_id
             and pa.workspace_product_id = rl.workspace_product_id),
         '{}'
       ) as aliases
from rfq_response resp
join rfq_recipient rec
  on rec.tenant_id = resp.tenant_id and rec.id = resp.rfq_recipient_id
join rfq_line rl
  on rl.tenant_id = rec.tenant_id and rl.rfq_id = rec.rfq_id
join workspace_product wp
  on wp.tenant_id = rl.tenant_id and wp.id = rl.workspace_product_id
left join canonical_product cp on cp.id = wp.canonical_product_id
left join lateral (
  -- Newest pack wins, the rule the requests module applies to a product's purchasing pack.
  select pd.base_quantity
  from pack_definition pd
  where pd.tenant_id = rl.tenant_id and pd.workspace_product_id = rl.workspace_product_id
  order by pd.created_at desc, pd.id desc
  limit 1
) pack on true
where resp.quotation_id = %s
order by rl.position, rl.created_at, rl.id
"""


@dataclass(frozen=True)
class RfqLineContext:
    rfq_line_id: UUID
    position: int
    workspace_product_id: UUID
    product_name: str
    quantity: Decimal
    base_unit: str | None
    pack_base_quantity: Decimal | None
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class RfqContext:
    rfq_id: UUID
    lines: tuple[RfqLineContext, ...]


def rfq_lines_for_quotation_with_conn(
    conn: psycopg.Connection, quotation_id: UUID
) -> RfqContext | None:
    """Read on a connection already scoped to the member (role and JWT claims set)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(RFQ_LINES_FOR_QUOTATION_SQL, (quotation_id,))
        rows = cur.fetchall()
    if not rows:
        return None
    rfq_ids = {row["rfq_id"] for row in rows}
    if len(rfq_ids) != 1:
        # A quotation answers at most one RFQ recipient today; refuse to guess if that changes.
        return None
    return RfqContext(
        rfq_id=rows[0]["rfq_id"],
        lines=tuple(
            RfqLineContext(
                rfq_line_id=row["rfq_line_id"],
                position=int(row["position"]),
                workspace_product_id=row["workspace_product_id"],
                product_name=str(row["product_name"]),
                quantity=Decimal(str(row["quantity"])),
                base_unit=row["base_unit"],
                pack_base_quantity=(
                    Decimal(str(row["pack_base_quantity"]))
                    if row["pack_base_quantity"] is not None
                    else None
                ),
                aliases=tuple(row["aliases"] or ()),
            )
            for row in rows
        ),
    )


def rfq_lines_for_quotation(
    settings: Settings, member: CurrentMember, quotation_id: UUID
) -> RfqContext | None:
    """The RFQ a quotation answers and the lines it asked for, or None."""
    from procurepilot_api.modules.rfq.service import _authenticated_db

    with _authenticated_db(settings, member) as conn:
        return rfq_lines_for_quotation_with_conn(conn, quotation_id)
