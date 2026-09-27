"""Read-only RFQ guardrail evaluation shared by the worker and response API."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from procurepilot_api.modules.catalogue.normalisation import normalised_base_quantity
from procurepilot_api.modules.rfq.guardrails import (
    AutoPreparationGuardrail,
    GuardrailCandidate,
    GuardrailCandidateLine,
    GuardrailDecision,
    GuardrailEvaluationInput,
    evaluate_guardrail,
)


@dataclass
class GuardrailEvaluationSnapshot:
    rfq_status: str
    needed_by_date: date
    guardrails: list[AutoPreparationGuardrail]
    total_response_count: int
    candidates: list[GuardrailCandidate]
    recent_average_price_by_product: dict[UUID, Decimal]
    decisions: dict[UUID, GuardrailDecision]
    responses_pending: bool


def compute_guardrail_evaluation(
    cur: psycopg.Cursor[Any],
    *,
    tenant_id: UUID,
    rfq_id: UUID,
) -> GuardrailEvaluationSnapshot | None:
    """Perform all guardrail reads/calculation, without locks or writes."""
    cur.execute(
        "select status, needed_by_date from rfq where id = %s and tenant_id = %s",
        (rfq_id, tenant_id),
    )
    rfq_row = cur.fetchone()
    if not rfq_row:
        return None

    cur.execute(
        "select id, tenant_id, enabled, min_response_count, max_order_value_amount, "
        "max_order_value_currency, max_price_variance_pct, supplier_allowlist, "
        "category_allowlist, default_branch_id, created_by_membership_id, created_at "
        "from auto_preparation_guardrail where tenant_id = %s and enabled = true",
        (tenant_id,),
    )
    guardrails = [AutoPreparationGuardrail(**row) for row in cur.fetchall()]
    if not guardrails:
        return GuardrailEvaluationSnapshot(
            rfq_status=rfq_row["status"],
            needed_by_date=rfq_row["needed_by_date"],
            guardrails=[],
            total_response_count=0,
            candidates=[],
            recent_average_price_by_product={},
            decisions={},
            responses_pending=False,
        )

    cur.execute(
        """
        select count(distinct r.id) as cnt
        from rfq_response r
        join rfq_recipient rec on r.rfq_recipient_id = rec.id
        join quotation q on q.id = r.quotation_id and q.tenant_id = r.tenant_id
        where rec.rfq_id = %s and r.tenant_id = %s
          and q.deleted_at is null and q.status <> 'refused'
        """,
        (rfq_id, tenant_id),
    )
    total_responses = cur.fetchone()["cnt"]

    cur.execute(
        """
        select r.id as response_id, r.created_at as captured_at, rec.supplier_id,
               q.status as quotation_status, q.deleted_at as quotation_deleted_at,
               ql.id as ql_id, ql.quantity, ql.pack_count, ql.unit_size,
               ql.unit_price_amount, ql.unit_price_currency,
               md.matched_workspace_product_id
        from rfq_response r
        join rfq_recipient rec on r.rfq_recipient_id = rec.id
        join quotation q on r.quotation_id = q.id and q.tenant_id = r.tenant_id
        left join quotation_line ql on r.quotation_id = ql.quotation_id
        left join match_decision md on ql.id = md.quotation_line_id
        where r.tenant_id = %s and rec.rfq_id = %s
        """,
        (tenant_id, rfq_id),
    )
    rows = cur.fetchall()

    response_state: dict[UUID, dict[str, object]] = {}
    for row in rows:
        state = response_state.setdefault(
            row["response_id"],
            {
                "status": row["quotation_status"],
                "deleted_at": row["quotation_deleted_at"],
                "line_count": 0,
                "decision_count": 0,
            },
        )
        if row["ql_id"]:
            state["line_count"] = int(state["line_count"]) + 1
            if row["matched_workspace_product_id"]:
                state["decision_count"] = int(state["decision_count"]) + 1

    responses_pending = any(
        state["status"] not in ("refused", "deleted")
        and state["deleted_at"] is None
        and not (state["status"] == "reviewed" and state["line_count"] == state["decision_count"])
        for state in response_state.values()
    )

    cur.execute(
        "select count(*) as cnt from rfq_line where tenant_id = %s and rfq_id = %s",
        (tenant_id, rfq_id),
    )
    rfq_line_count = cur.fetchone()["cnt"]

    matched_product_ids = {
        row["matched_workspace_product_id"]
        for row in rows
        if row["ql_id"] and row["matched_workspace_product_id"]
    }
    base_quantity_by_product: dict[UUID, Decimal] = {}
    if matched_product_ids:
        cur.execute(
            "select workspace_product_id, base_quantity from pack_definition "
            "where tenant_id = %s and workspace_product_id = any(%s)",
            (tenant_id, list(matched_product_ids)),
        )
        for row in cur.fetchall():
            base_quantity_by_product[row["workspace_product_id"]] = row["base_quantity"]

    candidates_by_id: dict[UUID, dict[str, object]] = {}
    workspace_product_ids: set[UUID] = set()
    for row in rows:
        response_id = row["response_id"]
        state = response_state[response_id]
        response_status = (
            "archived"
            if state["deleted_at"] is not None
            else "refused"
            if state["status"] == "refused"
            else "active"
        )
        candidate = candidates_by_id.setdefault(
            response_id,
            {
                "rfq_response_id": response_id,
                "supplier_id": row["supplier_id"],
                "currency": None,
                "total_amount": Decimal("0"),
                "matched_workspace_product_ids_set": set(),
                "matched_lines": [],
                "captured_at": row["captured_at"],
                "response_state": response_status,
            },
        )
        if row["ql_id"] and row["matched_workspace_product_id"] and response_status == "active":
            if candidate["currency"] is None:
                candidate["currency"] = row["unit_price_currency"]
            product_id = row["matched_workspace_product_id"]
            base_quantity = (
                normalised_base_quantity(row["pack_count"], row["unit_size"])
                if row["pack_count"] is not None and row["unit_size"] is not None
                else base_quantity_by_product.get(product_id)
            )
            unit_price = (
                row["unit_price_amount"] / base_quantity
                if base_quantity
                else row["unit_price_amount"]
            )
            candidate["matched_lines"].append(
                GuardrailCandidateLine(
                    workspace_product_id=product_id, unit_price_amount=unit_price
                )
            )
            candidate["total_amount"] += row["quantity"] * row["unit_price_amount"]
            candidate["matched_workspace_product_ids_set"].add(product_id)
            workspace_product_ids.add(product_id)

    candidates = [
        GuardrailCandidate(
            rfq_response_id=item["rfq_response_id"],
            supplier_id=item["supplier_id"],
            currency=item["currency"] or "",
            total_amount=item["total_amount"],
            all_lines_matched=(
                item["response_state"] == "active"
                and rfq_line_count > 0
                and len(item["matched_workspace_product_ids_set"]) == rfq_line_count
            ),
            matched_lines=item["matched_lines"],
            captured_at=item["captured_at"],
            response_state=item["response_state"],
        )
        for item in candidates_by_id.values()
    ]

    baseline: dict[UUID, Decimal] = {}
    if workspace_product_ids:
        cur.execute(
            """
            select md.matched_workspace_product_id,
                   avg(lc.total_amount / lc.normalised_base_quantity) as avg_price
            from landed_cost lc
            join match_decision md on lc.match_decision_id = md.id
            where lc.tenant_id = %s and lc.created_at >= now() - interval '90 days'
              and md.matched_workspace_product_id = any(%s)
              and not exists (
                select 1 from quotation_line candidate_ql
                join rfq_response candidate_response
                  on candidate_response.quotation_id = candidate_ql.quotation_id
                 and candidate_response.tenant_id = candidate_ql.tenant_id
                join rfq_recipient candidate_recipient
                  on candidate_recipient.id = candidate_response.rfq_recipient_id
                 and candidate_recipient.tenant_id = candidate_response.tenant_id
                where candidate_ql.id = lc.quotation_line_id
                  and candidate_recipient.rfq_id = %s
                  and candidate_response.tenant_id = %s
              )
            group by md.matched_workspace_product_id
            """,
            (tenant_id, list(workspace_product_ids), rfq_id, tenant_id),
        )
        for row in cur.fetchall():
            baseline[row["matched_workspace_product_id"]] = row["avg_price"]

    decisions: dict[UUID, GuardrailDecision] = {}
    if not responses_pending:
        for guardrail in guardrails:
            decisions[guardrail.id] = evaluate_guardrail(
                GuardrailEvaluationInput(
                    guardrail=guardrail,
                    rfq_status=rfq_row["status"],
                    total_response_count=total_responses,
                    candidates=[item for item in candidates if item.response_state == "active"],
                    recent_average_price_by_product=baseline,
                )
            )

    return GuardrailEvaluationSnapshot(
        rfq_status=rfq_row["status"],
        needed_by_date=rfq_row["needed_by_date"],
        guardrails=guardrails,
        total_response_count=total_responses,
        candidates=candidates,
        recent_average_price_by_product=baseline,
        decisions=decisions,
        responses_pending=responses_pending,
    )
