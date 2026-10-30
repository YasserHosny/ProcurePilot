"""Build an advisory advanced basket from one RFQ's reviewed replies (spec 024)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

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
    SplitPrepareRequest,
    SplitPrepareResponse,
)
from procurepilot_api.shared.logging import get_trace_id


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


def split_is_stale(
    quotation_ids: list[str],
    source_landed_cost_ids: list[str],
    eligible_quotation_ids: list[str],
    current_landed_cost_ids: list[str | None],
) -> bool:
    """R6: the eligible input set and every used product's price must still be current."""
    source_ids = set(source_landed_cost_ids)
    return sorted(quotation_ids) != sorted(eligible_quotation_ids) or any(
        cost_id is None or cost_id not in source_ids for cost_id in current_landed_cost_ids
    )


def base_to_packs(quantity: Decimal, base_quantity: Decimal) -> Decimal:
    packs = quantity / base_quantity
    whole = packs.to_integral_value()
    if whole <= 0 or abs(packs - whole) > Decimal("0.000001"):
        raise ConflictError(details={"reason": "allocation_not_whole_packs"})
    return whole


def _prepared_group(cur: psycopg.Cursor, key: UUID, basket_id: UUID) -> SplitPrepareResponse | None:
    cur.execute(
        """
        select g.id,g.basket_split_job_id,
          array_agg(pr.id order by pr.created_at,pr.id) as purchase_request_ids
        from purchase_request_group g
        join purchase_request pr on pr.request_group_id=g.id and pr.tenant_id=g.tenant_id
        where g.idempotency_key=%s group by g.id
        """,
        (key,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    if row["basket_split_job_id"] != basket_id:
        raise ConflictError(details={"reason": "idempotency_key_reused"})
    return SplitPrepareResponse(
        request_group_id=row["id"], purchase_request_ids=row["purchase_request_ids"]
    )


def prepare_requests_from_split(
    member: CurrentMember,
    basket_id: UUID,
    payload: SplitPrepareRequest,
    idempotency_key: UUID,
) -> tuple[SplitPrepareResponse, bool]:
    """Prepare one supplier draft per allocation, holding the shared RFQ lock until commit."""
    import json
    from datetime import date

    from procurepilot_api.config import get_settings
    from procurepilot_api.modules.offers.service import _authenticated_db
    from procurepilot_api.modules.requests.service import (
        create_requests_for_group,
        validate_group_destination,
    )
    from procurepilot_api.modules.rfq import service as rfq_service

    with _authenticated_db(get_settings(), member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            replay = _prepared_group(cur, idempotency_key, basket_id)
            if replay:
                return replay, False
            cur.execute("select * from basket_split_job where id=%s", (basket_id,))
            job = cur.fetchone()
            if job is None:
                raise NotFoundError(details={"resource": "basket_split_job"})
            if job["rfq_id"] is None:
                raise ConflictError(details={"reason": "not_rfq_split"})
            rfq_id = job["rfq_id"]
            status = rfq_service.lock_rfq_for_preparation(
                cur, tenant_id=member.tenant_id, rfq_id=rfq_id
            )
            if status is None:
                raise NotFoundError(details={"resource": "rfq"})
            # A simultaneous retry may have committed while we waited for the RFQ lock.
            replay = _prepared_group(cur, idempotency_key, basket_id)
            if replay:
                return replay, False
            if status == "converted":
                cur.execute(
                    "select id from purchase_request where source_rfq_id=%s order by created_at,id",
                    (rfq_id,),
                )
                raise ConflictError(
                    details={
                        "reason": "rfq_already_converted",
                        "purchase_request_ids": [str(row["id"]) for row in cur.fetchall()],
                    }
                )
            if job["status"] != "completed" or not job["result"] or not job["result"]["feasible"]:
                raise ConflictError(details={"reason": "split_not_completed"})
            result = job["result"]
            snapshot = job["request_snapshot"]["rfq"]
            cur.execute(
                """
                select r.id as response_id,q.id as quotation_id,rec.supplier_id,q.expiry_date
                from rfq_response r
                join rfq_recipient rec on rec.id=r.rfq_recipient_id
                join supplier s on s.id=rec.supplier_id and s.status in ('active','preferred')
                join quotation q on q.id=r.quotation_id
                where rec.rfq_id=%s and q.status='reviewed' and q.deleted_at is null
                  and exists (select 1 from quotation_line ql where ql.quotation_id=q.id)
                  and not exists (
                    select 1 from quotation_line ql
                    left join current_match_decision md on md.quotation_line_id=ql.id
                    where ql.quotation_id=q.id and md.matched_workspace_product_id is null)
                order by r.created_at,r.id
                """,
                (rfq_id,),
            )
            replies = cur.fetchall()
            # Expired evidence still belongs to this split; confirmation below gates its use.
            # Draft valuation also checks that each source cost has not been replaced.
            cur.execute(
                """
                select distinct on (rec.supplier_id,md.matched_workspace_product_id)
                  rec.supplier_id,md.matched_workspace_product_id as product_id,lc.id,
                  r.id as response_id
                from rfq_response r
                join rfq_recipient rec on rec.id=r.rfq_recipient_id
                join quotation_line ql on ql.quotation_id=r.quotation_id
                join current_match_decision md on md.quotation_line_id=ql.id
                left join landed_cost lc on lc.match_decision_id=md.id
                  and lc.id=any(%s::uuid[])
                where rec.rfq_id=%s and r.id=any(%s::uuid[])
                order by rec.supplier_id,md.matched_workspace_product_id,
                         lc.recorded_at desc nulls last,lc.id desc
                """,
                (
                    result["source_landed_cost_ids"],
                    rfq_id,
                    [reply["response_id"] for reply in replies],
                ),
            )
            costs = {
                (str(row["supplier_id"]), str(row["product_id"])): row for row in cur.fetchall()
            }
            current_cost_ids = [
                str(cost["id"]) if cost and cost["id"] else None
                for allocation in result["allocation"]
                for line in allocation["lines"]
                for cost in [costs.get((allocation["supplier_id"], line["workspace_product_id"]))]
            ]
            if split_is_stale(
                snapshot["price_quotation_ids"],
                result["source_landed_cost_ids"],
                [str(reply["quotation_id"]) for reply in replies],
                current_cost_ids,
            ):
                raise ConflictError(details={"reason": "split_stale"})
            # One draft has one source response. Resolve it from the actual priced offers,
            # since US1 permits several eligible quotations from the same supplier.
            response_by_supplier = {}
            for allocation in result["allocation"]:
                if not allocation["lines"]:
                    continue
                source_responses = {
                    costs[(allocation["supplier_id"], line["workspace_product_id"])]["response_id"]
                    for line in allocation["lines"]
                }
                if len(source_responses) != 1 or any(
                    str(costs[(allocation["supplier_id"], line["workspace_product_id"])]["id"])
                    != line["offer_id"]
                    for line in allocation["lines"]
                ):
                    raise ConflictError(details={"reason": "split_stale"})
                response_by_supplier[allocation["supplier_id"]] = source_responses.pop()
            used_replies = [r for r in replies if r["response_id"] in response_by_supplier.values()]
            unconfirmed = [
                str(r["quotation_id"])
                for r in used_replies
                if r["expiry_date"] is not None
                and r["expiry_date"] < date.today()
                and r["quotation_id"] not in payload.confirm_expired_quotation_ids
            ]
            if unconfirmed:
                raise ConflictError(
                    details={
                        "reason": "expired_quotation_unconfirmed",
                        "quotation_ids": unconfirmed,
                    }
                )
            cur.execute(
                "select workspace_product_id from rfq_line where rfq_id=%s order by "
                "position,created_at,id",
                (rfq_id,),
            )
            positions = {
                str(row["workspace_product_id"]): i for i, row in enumerate(cur.fetchall())
            }
            allocations = []
            for allocation in result["allocation"]:
                if not allocation["lines"]:
                    continue
                reply = next(
                    r
                    for r in used_replies
                    if r["response_id"] == response_by_supplier[allocation["supplier_id"]]
                )
                allocations.append(
                    {
                        "response_id": reply["response_id"],
                        "cost_centre_id": payload.cost_centre_id,
                        "required_by_date": payload.required_by_date,
                        "lines": [
                            {
                                "workspace_product_id": UUID(line["workspace_product_id"]),
                                "source_landed_cost_id": UUID(line["offer_id"]),
                                "quantity": base_to_packs(
                                    Decimal(line["quantity"]),
                                    Decimal(
                                        snapshot["pack_base_quantities"][
                                            line["workspace_product_id"]
                                        ]
                                    ),
                                ),
                                "pack_base_quantity": Decimal(
                                    snapshot["pack_base_quantities"][line["workspace_product_id"]]
                                ),
                            }
                            for line in sorted(
                                allocation["lines"],
                                key=lambda line: positions[line["workspace_product_id"]],
                            )
                        ],
                    }
                )
            validate_group_destination(conn, member, payload.branch_id, payload.cost_centre_id)
            total = result["total_landed_cost"]
            baselines = [
                Decimal(b["total_landed_cost"]["amount"])
                for b in result["single_supplier_baselines"]
                if b["feasible"] and b["total_landed_cost"]
            ]
            best = min(baselines) if baselines else None
            saving = max(Decimal(0), best - Decimal(total["amount"])) if best is not None else None
            group = {
                "id": uuid4(),
                "rfq_id": rfq_id,
                "basket_split_job_id": basket_id,
                "branch_id": payload.branch_id,
                "combined_total_currency": total["currency"],
                "best_single_total_amount": best,
                "best_single_total_currency": total["currency"] if best is not None else None,
                "saving_amount": saving,
                "saving_currency": total["currency"] if saving is not None else None,
                "idempotency_key": idempotency_key,
            }
            request_ids, combined = create_requests_for_group(conn, member, group, allocations)
            total = {"amount": str(combined), "currency": total["currency"]}
            rfq_service.mark_converted(cur, rfq_id=rfq_id, purchase_request_id=request_ids[0])
            # Match replay's stable ordering, independent of the solver's supplier ordering.
            request_ids = sorted(request_ids)
            response = SplitPrepareResponse(
                request_group_id=group["id"], purchase_request_ids=request_ids
            )
            cur.execute(
                "select record_audit_event(%s,'success'::audit_outcome,%s,%s,%s,%s::jsonb,%s)",
                (
                    "requests.group_prepared",
                    member.tenant_id,
                    member.membership_id,
                    member.email,
                    json.dumps(
                        {
                            **response.model_dump(mode="json"),
                            "rfq_id": str(rfq_id),
                            "basket_split_job_id": str(basket_id),
                            "rfq_response_ids": [str(r["response_id"]) for r in used_replies],
                            "price_quotation_ids": [str(r["quotation_id"]) for r in used_replies],
                            "combined_total": total,
                            "best_single_total": {
                                "amount": str(best),
                                "currency": total["currency"],
                            }
                            if best is not None
                            else None,
                            "saving": {"amount": str(saving), "currency": total["currency"]}
                            if saving is not None
                            else None,
                        }
                    ),
                    get_trace_id(),
                ),
            )
        return response, True
