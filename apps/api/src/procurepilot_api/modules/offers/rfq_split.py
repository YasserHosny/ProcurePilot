"""Build an advisory advanced basket from one RFQ's reviewed replies (spec 024)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.offers.basket_service import BasketService
from procurepilot_api.modules.offers.schemas import (
    AdvancedBasketOptimiseRequest,
    BasketItemRequest,
    BasketSplitJob,
    OptimisationWeights,
)


def build_rfq_split_request(
    conn: psycopg.Connection,
    member: CurrentMember,
    rfq_id: UUID,
) -> tuple[AdvancedBasketOptimiseRequest, dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select status from rfq where id = %s and tenant_id = %s", (rfq_id, member.tenant_id)
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "rfq"})
        if row["status"] == "converted":
            raise ConflictError(details={"reason": "rfq_already_converted"})
        cur.execute(
            """
            select r.id as response_id, q.id as quotation_id, rec.supplier_id,
                   q.status, q.deleted_at, count(ql.id) as line_count,
                   count(ql.id) filter (where md.matched_workspace_product_id is null)
                     as unmatched_count,
                   array_remove(array_agg(distinct ql.unit_price_currency), null)
                     || array[q.currency] as currencies
            from rfq_response r
            join rfq_recipient rec on rec.id = r.rfq_recipient_id
            join supplier s on s.id = rec.supplier_id and s.tenant_id = r.tenant_id
            join quotation q on q.id = r.quotation_id
            left join quotation_line ql on ql.quotation_id = q.id
            left join current_match_decision md on md.quotation_line_id = ql.id
            where rec.rfq_id = %s and r.tenant_id = %s and s.status in ('active', 'preferred')
            group by r.id, q.id, rec.supplier_id
            order by r.created_at, r.id
            """,
            (rfq_id, member.tenant_id),
        )
        replies = cur.fetchall()
        active = [
            reply
            for reply in replies
            if reply["status"] not in ("refused", "deleted") and reply["deleted_at"] is None
        ]
        unmatched = [str(reply["quotation_id"]) for reply in active if reply["unmatched_count"]]
        eligible_replies = [
            reply
            for reply in active
            if reply["status"] == "reviewed"
            and reply["line_count"]
            and not reply["unmatched_count"]
        ]
        eligible_by_supplier: dict[UUID, dict[str, object]] = {}
        for reply in eligible_replies:
            eligible_by_supplier[reply["supplier_id"]] = reply
        eligible = list(eligible_by_supplier.values())
        if len(eligible) < 2:
            raise ConflictError(
                details={
                    "reason": "not_enough_replies",
                    "eligible": len(eligible),
                    "unmatched_quotation_ids": unmatched,
                }
            )
        currencies = {currency for reply in eligible_replies for currency in reply["currencies"]}
        if len(currencies) != 1 or None in currencies:
            raise ConflictError(details={"reason": "mixed_currency"})
        cur.execute(
            """
            select rl.workspace_product_id, rl.quantity, pd.base_quantity
            from rfq_line rl
            left join lateral (
                select base_quantity from pack_definition
                where workspace_product_id = rl.workspace_product_id
                order by created_at desc, id desc limit 1
            ) pd on true
            where rl.rfq_id = %s and rl.tenant_id = %s
            order by rl.position, rl.created_at, rl.id
            """,
            (rfq_id, member.tenant_id),
        )
        lines = cur.fetchall()
    if any(line["base_quantity"] is None for line in lines):
        raise UnprocessableEntityError(details={"reason": "pack_definition_required"})
    payload = AdvancedBasketOptimiseRequest(
        supplier_ids=[reply["supplier_id"] for reply in eligible],
        items=[
            BasketItemRequest(
                workspace_product_id=line["workspace_product_id"],
                quantity=f"{Decimal(line['quantity']) * Decimal(line['base_quantity']):.6f}",
            )
            for line in lines
        ],
        risk_tolerance="high",
        urgency="normal",
        weights=OptimisationWeights(price=1, preferred_supplier=0, risk=0, lead_time=0, quality=0),
    )
    return payload, {
        "rfq_id": str(rfq_id),
        "price_quotation_ids": [str(reply["quotation_id"]) for reply in eligible_replies],
        "rfq_response_ids": [str(reply["response_id"]) for reply in eligible],
        "pack_base_quantities": {
            str(line["workspace_product_id"]): str(line["base_quantity"]) for line in lines
        },
    }


def start_rfq_split(
    *,
    member: CurrentMember,
    rfq_id: UUID,
    idempotency_key: UUID,
    service: BasketService | None = None,
    bearer_token: str | None = None,
) -> BasketSplitJob:
    # BasketService holds the RFQ preparation lock through eligibility, insertion and
    # the offers.rfq_split_started audit, and queues only after that transaction commits.
    job, _created = (service or BasketService()).create_job(
        member=member,
        rfq_id=rfq_id,
        idempotency_key=idempotency_key,
        bearer_token=bearer_token,
    )
    return job
