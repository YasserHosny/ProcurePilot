from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_optimiser_worker.models import (
    AdvancedBasketRequest,
    AdvancedOfferInput,
    AdvancedOptimisationInput,
    BasketItem,
    BasketJob,
    Money,
    OfferInput,
    OptimisationHardConstraints,
    OptimisationSoftWeights,
    QuantityTier,
    SupplierCommercialTerms,
    SupplierRiskSignal,
)


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


def load_advanced_optimisation_input(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    tenant_id: UUID,
) -> AdvancedOptimisationInput:
    row, snapshot = _load_advanced_job_snapshot(conn, job_id=job_id, tenant_id=tenant_id)
    request = _advanced_request_from_snapshot(row=row, snapshot=snapshot)
    supplier_terms = _supplier_terms_from_snapshot(snapshot)
    return AdvancedOptimisationInput(
        request=request,
        offers=read_current_advanced_offers(conn, request=request),
        supplier_terms=supplier_terms or read_supplier_terms(conn, request=request),
        supplier_risks=read_supplier_risks(conn, request=request),
    )


def load_advanced_request(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    tenant_id: UUID,
) -> AdvancedBasketRequest:
    row, snapshot = _load_advanced_job_snapshot(conn, job_id=job_id, tenant_id=tenant_id)
    return _advanced_request_from_snapshot(row=row, snapshot=snapshot)


def _load_advanced_job_snapshot(
    conn: psycopg.Connection,
    *,
    job_id: UUID,
    tenant_id: UUID,
) -> tuple[dict[str, object], dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, supplier_ids, items, request_snapshot
            from basket_split_job
            where id = %s and tenant_id = %s
            """,
            (job_id, tenant_id),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("advanced basket job not found")
    snapshot = row["request_snapshot"]
    if not isinstance(snapshot, dict):
        raise RuntimeError("advanced basket job is missing request_snapshot")
    return dict(row), snapshot


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


def read_current_advanced_offers(
    conn: psycopg.Connection,
    *,
    request: AdvancedBasketRequest,
) -> list[AdvancedOfferInput]:
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
                (lc.total_amount / lc.normalised_base_quantity) as unit_landed_cost,
                (lc.total_amount / lc.normalised_base_quantity * req.quantity) as projected_total,
                lc.id as source_landed_cost_id,
                (s.status = 'preferred'
                  or wp.preferred_supplier_id = q.supplier_id) as preferred,
                s.lead_time_days,
                row_number() over (
                  partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
                  order by lc.recorded_at desc, lc.id desc
                ) as rn
              from requested req
              join workspace_product wp on wp.id = req.workspace_product_id
              join match_decision md on md.matched_workspace_product_id = req.workspace_product_id
              join landed_cost lc on lc.match_decision_id = md.id
              join quotation_line ql on ql.id = lc.quotation_line_id
              join quotation q on q.id = ql.quotation_id
              join supplier s on s.id = q.supplier_id
              where lc.tenant_id = %s
                and wp.tenant_id = %s
                and q.supplier_id = any(%s::uuid[])
                and q.status = 'reviewed'
                and s.status in ('active', 'preferred')
                and (lc.valid_to is null or lc.valid_to >= now())
            )
            select * from ranked where rn = 1
            """,
            (
                Jsonb([item.model_dump(mode="json") for item in request.items]),
                request.tenant_id,
                request.tenant_id,
                [str(supplier_id) for supplier_id in request.supplier_ids],
            ),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return [_advanced_offer(row) for row in rows]


def read_supplier_terms(
    conn: psycopg.Connection,
    *,
    request: AdvancedBasketRequest,
) -> list[SupplierCommercialTerms]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select distinct on (supplier_id)
              id,
              supplier_id,
              effective_from,
              effective_to,
              minimum_order_value_amount,
              minimum_order_value_currency,
              delivery_fee_amount,
              delivery_fee_currency,
              free_delivery_threshold_amount,
              free_delivery_threshold_currency,
              quantity_tiers,
              rule_version
            from supplier_commercial_term
            where tenant_id = %s
              and supplier_id = any(%s::uuid[])
              and effective_from <= now()
              and (effective_to is null or effective_to > now())
            order by supplier_id, effective_from desc, created_at desc, id desc
            """,
            (request.tenant_id, [str(supplier_id) for supplier_id in request.supplier_ids]),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return [_supplier_terms(row) for row in rows]


def read_supplier_risks(
    conn: psycopg.Connection,
    *,
    request: AdvancedBasketRequest,
) -> list[SupplierRiskSignal]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select distinct on (supplier_id)
              id,
              supplier_id,
              risk_score,
              source_counts,
              rule_version
            from supplier_scorecard_snapshot
            where tenant_id = %s
              and supplier_id = any(%s::uuid[])
            order by supplier_id, window_end desc, computed_at desc, id desc
            """,
            (request.tenant_id, [str(supplier_id) for supplier_id in request.supplier_ids]),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return [_supplier_risk(row) for row in rows]


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


def _advanced_offer(row: dict[str, object]) -> AdvancedOfferInput:
    amount = Decimal(str(row["projected_total"])).quantize(Decimal("0.0001"))
    unit = Decimal(str(row["unit_landed_cost"])).quantize(Decimal("0.0001"))
    lead_time = row.get("lead_time_days")
    return AdvancedOfferInput(
        offer_id=UUID(str(row["offer_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        quantity=format(Decimal(str(row["requested_quantity"])).quantize(Decimal("0.000001")), "f"),
        total_landed_cost=Money(amount=format(amount, "f"), currency=str(row["total_currency"])),
        unit_landed_cost=Money(amount=format(unit, "f"), currency=str(row["total_currency"])),
        source_landed_cost_id=UUID(str(row["source_landed_cost_id"])),
        preferred=bool(row["preferred"]),
        lead_time_days=int(lead_time) if lead_time is not None else None,
    )


def _advanced_request_from_snapshot(
    *,
    row: dict[str, object],
    snapshot: dict[str, object],
) -> AdvancedBasketRequest:
    hard_constraints = _hard_constraints(snapshot)
    return AdvancedBasketRequest(
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        supplier_ids=[
            UUID(str(value))
            for value in snapshot.get("supplier_ids", row["supplier_ids"])
        ],
        items=[BasketItem.model_validate(item) for item in snapshot.get("items", row["items"])],
        hard_constraints=hard_constraints,
        soft_weights=OptimisationSoftWeights.model_validate(snapshot.get("soft_weights") or {}),
        rule_version=str(snapshot["rule_version"]),
    )


def _hard_constraints(snapshot: dict[str, object]) -> OptimisationHardConstraints:
    raw = snapshot.get("hard_constraints")
    data = dict(raw) if isinstance(raw, dict) else {}
    data["excluded_supplier_ids"] = snapshot.get(
        "excluded_supplier_ids",
        data.get("excluded_supplier_ids", []),
    )
    if "max_supplier_risk" not in data:
        risk_tolerance = snapshot.get("risk_tolerance", data.get("risk_tolerance"))
        data["max_supplier_risk"] = _risk_tolerance_to_max_score(risk_tolerance)
    data.pop("risk_tolerance", None)
    data.pop("urgency", None)
    return OptimisationHardConstraints.model_validate(data)


def _risk_tolerance_to_max_score(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return f"{Decimal(str(value)):.4f}"
    mapping = {"low": "0.2500", "medium": "0.5000", "high": "0.7500"}
    return mapping.get(str(value), str(value))


def _supplier_terms(row: dict[str, object]) -> SupplierCommercialTerms:
    return SupplierCommercialTerms(
        supplier_id=UUID(str(row["supplier_id"])),
        rule_version=str(row["rule_version"]),
        minimum_order_value=_money_pair(row, "minimum_order_value"),
        delivery_fee=_money_pair(row, "delivery_fee"),
        free_delivery_threshold=_money_pair(row, "free_delivery_threshold"),
        quantity_tiers=[
            QuantityTier.model_validate(tier) for tier in row.get("quantity_tiers", [])
        ],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
    )


def _supplier_terms_from_snapshot(
    snapshot: dict[str, object],
) -> list[SupplierCommercialTerms]:
    raw_terms = snapshot.get("supplier_terms")
    if not isinstance(raw_terms, list):
        return []
    terms = []
    for raw_term in raw_terms:
        if not isinstance(raw_term, dict):
            continue
        term_id = raw_term.get("id")
        data = dict(raw_term)
        data.pop("id", None)
        data["quantity_tiers"] = [
            _quantity_tier_from_snapshot(tier, term_id)
            for tier in data.get("quantity_tiers", [])
            if isinstance(tier, dict)
        ]
        terms.append(SupplierCommercialTerms.model_validate(data))
    return terms


def _quantity_tier_from_snapshot(
    tier: dict[str, object],
    source_term_id: object,
) -> dict[str, object]:
    data = dict(tier)
    if data.get("source_term_id") is None and source_term_id is not None:
        data["source_term_id"] = source_term_id
    return data


def _money_pair(row: dict[str, object], prefix: str) -> Money | None:
    amount = row.get(f"{prefix}_amount")
    currency = row.get(f"{prefix}_currency")
    if amount is None and currency is None:
        return None
    if amount is None or currency is None:
        raise RuntimeError(f"{prefix} money pair is incomplete")
    return Money(amount=f"{Decimal(str(amount)):.4f}", currency=str(currency))


def _supplier_risk(row: dict[str, object]) -> SupplierRiskSignal:
    risk_score = row["risk_score"]
    if not isinstance(risk_score, dict):
        raise RuntimeError("supplier risk score must be an object")
    source_counts = row["source_counts"] if isinstance(row["source_counts"], dict) else {}
    source_total = sum(int(value) for value in source_counts.values())
    confidence = str(risk_score.get("confidence", "0.5000"))
    if confidence in {"low", "medium", "high"}:
        confidence = {"low": "0.3000", "medium": "0.6000", "high": "0.9000"}[confidence]
    return SupplierRiskSignal(
        supplier_id=UUID(str(row["supplier_id"])),
        risk_score=str(risk_score.get("total", risk_score.get("score", "0.5000"))),
        confidence=confidence,
        insufficient_evidence=bool(
            risk_score.get("insufficient_evidence", source_total == 0)
        ),
        source_ids=[UUID(str(row["id"]))],
        rule_version=str(risk_score.get("rule_version", row["rule_version"])),
    )
