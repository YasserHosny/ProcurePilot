"""Tenant-scoped loading and atomic persistence for Supplier IQ v2."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.offers.schemas import SupplierRiskEvidenceRef, SupplierRiskResult
from procurepilot_api.modules.offers.supplier_iq_v2 import (
    Alternative,
    OrderLine,
    Price,
    PurchaseOrder,
    ReceiptLine,
    SupplierRiskInput,
)

__all__ = [
    "SupplierIqRepository",
    "load_risk_input",
    "persist_snapshot",
    "list_latest",
]

SnapshotRow = dict[str, object]
EvidenceKind = Literal[
    "concentration",
    "price_drift",
    "reliability",
    "single_source_exposure",
]


@dataclass(frozen=True)
class SnapshotWrite:
    snapshot_id: UUID
    created: bool


@dataclass(frozen=True)
class SnapshotPage:
    items: tuple[SnapshotRow, ...]
    next_cursor: str | None


def load_risk_input(
    conn: psycopg.Connection,
    *,
    supplier_id: UUID,
    window_start: date,
    window_end: date,
) -> SupplierRiskInput:
    """Load only rows visible to the connection's current tenant context."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select po.id, po.supplier_id, po.order_date, po.expected_delivery_date,
                   po.status::text as status, po.total_amount, po.total_currency,
                   pol.id as line_id, pol.workspace_product_id, pol.base_unit,
                   pol.ordered_quantity
            from purchase_order po
            left join purchase_order_line pol
              on pol.tenant_id = po.tenant_id and pol.purchase_order_id = po.id
            where po.order_date < %(window_end)s
            order by po.order_date, po.id, pol.line_number
            """,
            {"supplier_id": supplier_id, "window_end": window_end},
        )
        order_rows = [dict(row) for row in cur.fetchall()]

        order_ids = sorted({row["id"] for row in order_rows})
        cur.execute(
            """
            select drl.id, drl.purchase_order_id, drl.purchase_order_line_id,
                   drl.received_quantity, dr.receipt_date
            from delivery_receipt_line drl
            join delivery_receipt dr
              on dr.tenant_id = drl.tenant_id and dr.id = drl.delivery_receipt_id
            where drl.purchase_order_id = any(%(order_ids)s)
              and dr.receipt_date < %(window_end)s
            order by dr.receipt_date, drl.id
            """,
            {"order_ids": order_ids, "window_end": window_end},
        )
        receipt_rows = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            select lc.id, q.supplier_id, s.status::text as supplier_status,
                   md.matched_workspace_product_id as product_id,
                   lc.base_unit, lc.total_currency, lc.total_amount,
                   lc.normalised_base_quantity, lc.recorded_at, lc.valid_from, lc.valid_to
            from landed_cost lc
            join match_decision md
              on md.tenant_id = lc.tenant_id and md.id = lc.match_decision_id
            join quotation_line ql
              on ql.tenant_id = lc.tenant_id and ql.id = lc.quotation_line_id
            join quotation q
              on q.tenant_id = ql.tenant_id and q.id = ql.quotation_id
            join supplier s
              on s.tenant_id = q.tenant_id and s.id = q.supplier_id
            where q.supplier_id is not null
              and q.status = 'reviewed'
              and s.status in ('active', 'preferred')
              and lc.recorded_at < %(window_end)s
            order by lc.recorded_at, lc.id
            """,
            {"window_end": datetime.combine(window_end, time.min, tzinfo=UTC)},
        )
        price_rows = [dict(row) for row in cur.fetchall()]

    orders_by_id: dict[UUID, PurchaseOrder] = {}
    lines_by_order: dict[UUID, list[OrderLine]] = {}
    for row in order_rows:
        order_id = UUID(str(row["id"]))
        line_id = row.get("line_id")
        if line_id is not None and row["workspace_product_id"] is not None:
            lines_by_order.setdefault(order_id, []).append(
                OrderLine(
                    id=UUID(str(line_id)),
                    product_id=UUID(str(row["workspace_product_id"])),
                    base_unit=str(row["base_unit"]),
                    quantity=Decimal(str(row["ordered_quantity"])),
                )
            )
        orders_by_id[order_id] = PurchaseOrder(
            id=order_id,
            supplier_id=UUID(str(row["supplier_id"])),
            ordered_on=row["order_date"],
            expected_delivery_date=row["expected_delivery_date"],
            status=str(row["status"]),
            amount=Decimal(str(row["total_amount"])),
            currency=str(row["total_currency"]),
            lines=(),
        )
    orders = tuple(
        PurchaseOrder(**{**order.__dict__, "lines": tuple(lines_by_order.get(order.id, ()))})
        for order in orders_by_id.values()
    )

    receipts = tuple(
        ReceiptLine(
            id=UUID(str(row["id"])),
            purchase_order_id=UUID(str(row["purchase_order_id"])),
            purchase_order_line_id=UUID(str(row["purchase_order_line_id"])),
            quantity=Decimal(str(row["received_quantity"])),
            received_at=datetime.combine(row["receipt_date"], time.min, tzinfo=UTC),
        )
        for row in receipt_rows
    )
    prices = tuple(
        Price(
            id=UUID(str(row["id"])),
            supplier_id=UUID(str(row["supplier_id"])),
            product_id=UUID(str(row["product_id"])),
            base_unit=str(row["base_unit"]),
            currency=str(row["total_currency"]),
            unit_price=Decimal(str(row["total_amount"]))
            / Decimal(str(row["normalised_base_quantity"])),
            recorded_at=row["recorded_at"],
        )
        for row in price_rows
    )
    alternatives = tuple(
        Alternative(
            id=price.id,
            supplier_id=price.supplier_id,
            product_id=price.product_id,
            base_unit=price.base_unit,
            currency=price.currency,
            unit_price=price.unit_price,
            recorded_at=price.recorded_at,
            valid_from=row["valid_from"].date(),
            valid_to=row["valid_to"].date() if row["valid_to"] else None,
            active=True,
        )
        for price, row in zip(prices, price_rows, strict=True)
        if price.supplier_id != supplier_id
    )
    supplier_prices = tuple(price for price in prices if price.supplier_id == supplier_id)
    return SupplierRiskInput(
        supplier_id=supplier_id,
        window_start=window_start,
        window_end=window_end,
        purchase_orders=orders,
        receipts=receipts,
        prices=supplier_prices,
        alternatives=alternatives,
    )


def persist_snapshot(
    conn: psycopg.Connection,
    *,
    member: CurrentMember,
    result: SupplierRiskResult,
) -> SnapshotWrite:
    """Persist a v2 header, metrics, and typed evidence in the caller's transaction."""
    with conn.cursor() as cur:
        valid_from = result.window_end
        computed_at = datetime.now(UTC)
        result_json = result.model_dump(mode="json")
        cur.execute(
            """
            insert into supplier_scorecard_snapshot (
              tenant_id, supplier_id, window_start, window_end, rule_version,
              metrics, risk_score, source_counts, computed_at, computed_by_membership_id,
              state, confidence, release_posture, valid_from, valid_until,
              source_fingerprint, observed_history_days
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict do nothing
            returning id
            """,
            (
                member.tenant_id,
                result.supplier_id,
                result.window_start,
                result.window_end,
                result.scorecard_version,
                Jsonb(
                    {
                        name: component.model_dump(mode="json")
                        for name, component in result.components.items()
                    }
                ),
                Jsonb(
                    {
                        "total": result_json["score"],
                        "components": {
                            name: component["risk"]
                            for name, component in result_json["components"].items()
                        },
                        "weights": result_json["weights"],
                    }
                ),
                Jsonb(
                    {name: component.sample_count for name, component in result.components.items()}
                ),
                computed_at,
                member.membership_id,
                result.state,
                result.confidence,
                result.release_posture,
                datetime.combine(valid_from, time.min, tzinfo=UTC),
                computed_at + timedelta(days=1),
                result.source_fingerprint,
                result.observed_history_days,
            ),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "select id from supplier_scorecard_snapshot where source_fingerprint = %s",
                (result.source_fingerprint,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("snapshot insert did not return an id")
            return SnapshotWrite(UUID(str(existing[0])), False)
        snapshot_id = UUID(str(row[0]))
        for (
            metric_kind,
            bucket_key,
            component,
            source_refs,
            value,
            numerator,
            denominator,
            amount,
            currency,
        ) in _metric_rows(result):
            cur.execute(
                """
                insert into supplier_scorecard_metric (
                  tenant_id, snapshot_id, metric_kind, bucket_key, value, numerator, denominator,
                  amount, currency, sample_count, confidence, is_sufficient, window_start,
                  window_end, calculation_version
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    member.tenant_id,
                    snapshot_id,
                    metric_kind,
                    bucket_key,
                    value,
                    numerator,
                    denominator,
                    amount,
                    currency,
                    component.sample_count,
                    component.confidence,
                    not component.insufficient_evidence,
                    component.window_start,
                    component.window_end,
                    component.calculation_version,
                ),
            )
            metric_id = UUID(str(cur.fetchone()[0]))
            for source_ref in source_refs:
                target = _source_target(cur, source_ref)
                if target is None:
                    raise RuntimeError(f"unmapped Supplier IQ evidence source: {source_ref}")
                column, target_id = target
                cur.execute(
                    f"insert into supplier_scorecard_evidence "
                    f"(tenant_id, metric_id, {column}) values (%s, %s, %s)",
                    (member.tenant_id, metric_id, target_id),
                )
        return SnapshotWrite(snapshot_id, True)


def list_latest(
    conn: psycopg.Connection,
    *,
    cursor: str | None,
    limit: int,
) -> SnapshotPage:
    page_after = _decode_cursor(cursor)
    fetch_limit = min(100, max(1, limit))
    after_clause = ""
    query_params: list[object] = []
    if page_after is not None:
        after_clause = """
            and (ranked.window_end, ranked.computed_at, ranked.id)
              < (%s, %s, %s)
        """
        query_params.extend(page_after)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            with ranked as (
              select snapshot.id, snapshot.supplier_id, supplier.name as supplier_name,
                     snapshot.window_start,
                     snapshot.window_end, snapshot.state, snapshot.confidence,
                     snapshot.release_posture, snapshot.valid_from, snapshot.valid_until,
                     snapshot.source_fingerprint, snapshot.observed_history_days,
                     snapshot.risk_score, snapshot.computed_at,
                     row_number() over (
                       partition by snapshot.supplier_id
                       order by snapshot.window_end desc, snapshot.computed_at desc,
                                snapshot.id desc
                     ) as row_number
              from supplier_scorecard_snapshot snapshot
              join supplier
                on supplier.tenant_id = snapshot.tenant_id
               and supplier.id = snapshot.supplier_id
              where snapshot.rule_version = 'supplier-scorecard-v2'
                and supplier.status in ('active', 'preferred')
            )
            select id, supplier_id, supplier_name, window_start, window_end, state, confidence,
                   release_posture, valid_from, valid_until, source_fingerprint,
                   observed_history_days, risk_score,
                   case
                     when risk_score->>'total' is null then null
                     when (risk_score->>'total')::numeric < 0.35 then 'low'
                     when (risk_score->>'total')::numeric < 0.65 then 'medium'
                     else 'high'
                   end as risk_level,
                   computed_at
            from ranked
            where row_number = 1
              {after_clause}
            order by window_end desc, computed_at desc, id desc
            limit %s
            """,
            (*query_params, fetch_limit + 1),
        )
        rows = tuple(dict(row) for row in cur.fetchall())
    has_more = len(rows) > fetch_limit
    return SnapshotPage(
        items=rows[:fetch_limit],
        next_cursor=_encode_cursor(rows[fetch_limit - 1]) if has_more else None,
    )


class SupplierIqRepository:
    load_risk_input = staticmethod(load_risk_input)
    persist_snapshot = staticmethod(persist_snapshot)
    list_latest = staticmethod(list_latest)


def _encode_cursor(row: SnapshotRow) -> str:
    payload = {
        "window_end": row["window_end"].isoformat(),
        "computed_at": row["computed_at"].isoformat(),
        "id": str(row["id"]),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    return encoded.rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[date, datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if set(payload) != {"window_end", "computed_at", "id"}:
            raise ValueError("invalid cursor fields")
        window_end = date.fromisoformat(payload["window_end"])
        computed_at = datetime.fromisoformat(payload["computed_at"])
        snapshot_id = UUID(payload["id"])
    except (
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        from procurepilot_api.errors import UnprocessableEntityError

        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if computed_at.tzinfo is None:
        from procurepilot_api.errors import UnprocessableEntityError

        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return window_end, computed_at, snapshot_id


def _metric_rows(
    result: SupplierRiskResult,
) -> list[
    tuple[
        EvidenceKind,
        str,
        object,
        tuple[SupplierRiskEvidenceRef, ...],
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        str | None,
    ]
]:
    rows: list[
        tuple[
            EvidenceKind,
            str,
            object,
            tuple[SupplierRiskEvidenceRef, ...],
            Decimal | None,
            Decimal | None,
            Decimal | None,
            Decimal | None,
            str | None,
        ]
    ] = []
    concentration = result.components["concentration"]
    if not concentration.currency_buckets:
        rows.append(
            (
                "concentration",
                "default",
                concentration,
                (),
                concentration.value,
                None,
                None,
                None,
                None,
            )
        )
    for bucket in concentration.currency_buckets:
        rows.append(
            (
                "concentration",
                bucket.currency,
                concentration,
                _refs_for_ids(concentration.source_refs, bucket.source_ids),
                bucket.share,
                bucket.supplier_spend,
                bucket.tenant_spend,
                bucket.supplier_spend,
                bucket.currency,
            )
        )
    for result_kind, metric_kind in (
        ("price_drift", "price_drift"),
        ("reliability", "reliability"),
        ("single_source", "single_source_exposure"),
    ):
        component = result.components[result_kind]
        rows.append(
            (
                metric_kind,
                "default",
                component,
                component.source_refs,
                component.value,
                component.numerator,
                component.denominator,
                None,
                None,
            )
        )
    return rows


def _refs_for_ids(
    refs: tuple[SupplierRiskEvidenceRef, ...], source_ids: tuple[UUID, ...]
) -> tuple[SupplierRiskEvidenceRef, ...]:
    wanted = set(source_ids)
    return tuple(ref for ref in refs if ref.source_id in wanted)


def _source_target(
    cur: psycopg.Cursor, source_ref: SupplierRiskEvidenceRef
) -> tuple[str, UUID] | None:
    source_id = source_ref.source_id
    if source_ref.source_kind == "purchase_order":
        cur.execute("select id from purchase_order where id = %s", (source_id,))
        if cur.fetchone() is not None:
            return "purchase_order_id", source_id
    if source_ref.source_kind == "delivery_receipt_line":
        cur.execute(
            "select delivery_receipt_id from delivery_receipt_line where id = %s",
            (source_id,),
        )
        row = cur.fetchone()
        if row is not None:
            return "delivery_receipt_id", UUID(str(row[0]))
    if source_ref.source_kind == "landed_cost":
        cur.execute("select id from landed_cost where id = %s", (source_id,))
        if cur.fetchone() is not None:
            return "landed_cost_id", source_id
    if source_ref.source_kind == "workspace_product":
        cur.execute("select id from workspace_product where id = %s", (source_id,))
        if cur.fetchone() is not None:
            return "workspace_product_id", source_id
    return None
