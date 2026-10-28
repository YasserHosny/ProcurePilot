from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.modules.offers.price_history import (
    normalised_unit_price,
    price_history_summary,
)
from procurepilot_api.modules.offers.schemas import Money as OfferMoney
from procurepilot_api.modules.offers.schemas import PriceHistoryPoint
from procurepilot_api.modules.savings.schemas import Money

MONEY_QUANT = Decimal("0.0001")
QUANTITY_QUANT = Decimal("0.000001")
CALCULATION_VERSION = "saving-baseline-v2"

# Statuses of a purchase order a human has authorised and sent. Draft and cancelled orders are
# never a price that was paid.
PO_BASELINE_STATUSES = ("submitted", "confirmed", "partially_received", "received", "closed")

LAST_PO_PRICE_SQL = """
select
  pol.id as purchase_order_line_id,
  pol.purchase_order_id,
  po.order_number,
  po.order_date,
  pol.base_unit,
  pol.unit_price_amount,
  pol.unit_price_currency,
  pol.pack_base_quantity
from purchase_order_line pol
join purchase_order po
  on po.tenant_id = pol.tenant_id and po.id = pol.purchase_order_id
where pol.workspace_product_id = %(product_id)s
  and po.status::text = any(%(statuses)s)
  and (%(exclude_order_id)s::uuid is null or po.id <> %(exclude_order_id)s::uuid)
  -- A line in another base unit is not comparable without a conversion we do not have. Filter
  -- before the limit so newer lines in another unit can never hide a comparable one.
  and (%(base_unit)s::text is null or pol.base_unit = %(base_unit)s::text)
order by po.order_date desc, po.created_at desc, pol.created_at desc, pol.id desc
limit 1
"""

PRICE_HISTORY_SQL = """
select
  lc.id as landed_cost_id,
  md.matched_workspace_product_id as workspace_product_id,
  q.supplier_id,
  s.name as supplier_name,
  lc.recorded_at,
  lc.valid_from,
  lc.valid_to,
  lc.total_amount,
  lc.total_currency,
  lc.normalised_base_quantity,
  lc.quantity,
  lc.base_unit
from workspace_product wp
join current_match_decision md on md.matched_workspace_product_id = wp.id
join landed_cost lc on lc.match_decision_id = md.id
join quotation_line ql on ql.id = lc.quotation_line_id
join quotation q on q.id = ql.quotation_id
join supplier s on s.id = q.supplier_id
where wp.id = %(product_id)s
order by lc.recorded_at desc, lc.id desc
limit 100
"""


@dataclass(frozen=True)
class BaselineCapture:
    policy: str
    source_landed_cost_ids: list[UUID]
    unit_price: Money | None
    value: Money | None
    delta: Money | None
    calculation_inputs: dict[str, object]
    source_po_line_ids: list[UUID] | None = None


@dataclass(frozen=True)
class PoPrice:
    purchase_order_line_id: UUID
    purchase_order_id: UUID
    order_number: str
    unit_price: Money  # per pack, ADR-020
    pack_base_quantity: Decimal  # base units per pack; 1 when unpacked


def capture_baseline(
    conn: object,
    *,
    product_id: UUID,
    quantity: Decimal,
    actual: Money,
    base_unit: str | None = None,
    exclude_purchase_order_id: UUID | None = None,
) -> BaselineCapture:
    """Capture the baseline for an outcome of ``quantity`` base units costing ``actual``.

    Policy order: the last PO price for the product (excluding the order being recorded), then
    the latest quoted landed cost, then the 6-month rolling quoted average, then none.
    """
    po_price = _last_po_price(
        conn,
        product_id=product_id,
        base_unit=base_unit,
        exclude_purchase_order_id=exclude_purchase_order_id,
    )
    if po_price is not None:
        return _po_baseline(
            po_price,
            quantity=quantity,
            actual=actual,
            exclude_purchase_order_id=exclude_purchase_order_id,
        )
    points = _price_history_points(conn, product_id)
    summary = price_history_summary(
        points,
        window_start=_subtract_calendar_months(datetime.now(UTC), 6),
    )
    metric = summary.last_paid
    policy = "last_paid"
    if metric is None:
        metric = summary.average_paid_rolling_window
        policy = "rolling_average_6m"
    if metric is None:
        return BaselineCapture(
            policy="none_available",
            source_landed_cost_ids=[],
            unit_price=None,
            value=None,
            delta=None,
            calculation_inputs={
                "quantity": _quantity_string(quantity),
                "actual_value": actual.model_dump(mode="json"),
                "price_history_point_count": len(points),
            },
        )
    if metric.value.currency != actual.currency:
        return BaselineCapture(
            policy="none_available",
            source_landed_cost_ids=metric.source_landed_cost_ids,
            unit_price=Money(amount=Decimal(metric.value.amount), currency=metric.value.currency),
            value=None,
            delta=None,
            calculation_inputs={
                "quantity": _quantity_string(quantity),
                "actual_value": actual.model_dump(mode="json"),
                "baseline_currency": metric.value.currency,
                "actual_currency": actual.currency,
                "reason": "currency_mismatch",
            },
        )
    unit_price = Decimal(metric.value.amount)
    baseline_value = (unit_price * quantity).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    delta = (baseline_value - actual.amount).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return BaselineCapture(
        policy=policy,
        source_landed_cost_ids=metric.source_landed_cost_ids,
        unit_price=Money(amount=unit_price, currency=metric.value.currency),
        value=Money(amount=baseline_value, currency=metric.value.currency),
        delta=Money(amount=delta, currency=metric.value.currency),
        calculation_inputs={
            "quantity": _quantity_string(quantity),
            "actual_value": actual.model_dump(mode="json"),
            "selected_metric": policy,
            "source_landed_cost_ids": [str(item) for item in metric.source_landed_cost_ids],
            "price_history_point_count": len(points),
        },
    )


def _po_baseline(
    po_price: PoPrice,
    *,
    quantity: Decimal,
    actual: Money,
    exclude_purchase_order_id: UUID | None,
) -> BaselineCapture:
    # The PO line is priced per pack; the outcome quantity is in base units. Scale the pack price
    # by the number of packs the outcome represents rather than rounding a per-base-unit price.
    packs = quantity / po_price.pack_base_quantity
    unit_price = (po_price.unit_price.amount / po_price.pack_base_quantity).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    inputs: dict[str, object] = {
        "quantity": _quantity_string(quantity),
        "actual_value": actual.model_dump(mode="json"),
        "selected_metric": "last_po_price",
        "source_po_line_ids": [str(po_price.purchase_order_line_id)],
        "source_purchase_order_id": str(po_price.purchase_order_id),
        "source_order_number": po_price.order_number,
        "po_unit_price_per_pack": po_price.unit_price.model_dump(mode="json"),
        "pack_base_quantity": _quantity_string(po_price.pack_base_quantity),
        "excluded_purchase_order_id": (
            None if exclude_purchase_order_id is None else str(exclude_purchase_order_id)
        ),
    }
    if po_price.unit_price.currency != actual.currency:
        return BaselineCapture(
            policy="none_available",
            source_landed_cost_ids=[],
            source_po_line_ids=[po_price.purchase_order_line_id],
            unit_price=Money(amount=unit_price, currency=po_price.unit_price.currency),
            value=None,
            delta=None,
            calculation_inputs={
                **inputs,
                "baseline_currency": po_price.unit_price.currency,
                "actual_currency": actual.currency,
                "reason": "currency_mismatch",
            },
        )
    baseline_value = (po_price.unit_price.amount * packs).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    delta = (baseline_value - actual.amount).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    currency = po_price.unit_price.currency
    return BaselineCapture(
        policy="last_po_price",
        source_landed_cost_ids=[],
        source_po_line_ids=[po_price.purchase_order_line_id],
        unit_price=Money(amount=unit_price, currency=currency),
        value=Money(amount=baseline_value, currency=currency),
        delta=Money(amount=delta, currency=currency),
        calculation_inputs=inputs,
    )


def _last_po_price(
    conn: object,
    *,
    product_id: UUID,
    base_unit: str | None,
    exclude_purchase_order_id: UUID | None,
) -> PoPrice | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            LAST_PO_PRICE_SQL,
            {
                "product_id": product_id,
                "statuses": list(PO_BASELINE_STATUSES),
                "exclude_order_id": exclude_purchase_order_id,
                "base_unit": base_unit,
            },
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        pack = row.get("pack_base_quantity")
        return PoPrice(
            purchase_order_line_id=UUID(str(row["purchase_order_line_id"])),
            purchase_order_id=UUID(str(row["purchase_order_id"])),
            order_number=str(row["order_number"]),
            unit_price=Money(
                amount=Decimal(str(row["unit_price_amount"])),
                currency=str(row["unit_price_currency"]),
            ),
            pack_base_quantity=Decimal("1") if pack is None else Decimal(str(pack)),
        )
    return None


def _price_history_points(conn: object, product_id: UUID) -> list[PriceHistoryPoint]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(PRICE_HISTORY_SQL, {"product_id": product_id})
        rows = [dict(row) for row in cur.fetchall()]
    return [_history_point(row) for row in rows]


def _history_point(row: dict[str, object]) -> PriceHistoryPoint:
    unit = normalised_unit_price(row["total_amount"], row["normalised_base_quantity"])
    currency = str(row["total_currency"])
    return PriceHistoryPoint(
        landed_cost_id=UUID(str(row["landed_cost_id"])),
        workspace_product_id=UUID(str(row["workspace_product_id"])),
        supplier_id=UUID(str(row["supplier_id"])),
        supplier_name=str(row["supplier_name"]),
        recorded_at=row["recorded_at"],
        valid_from=row["valid_from"],
        valid_to=row.get("valid_to"),
        normalised_unit_price=OfferMoney(amount=format(unit, "f"), currency=currency),
        landed_cost_total=OfferMoney(amount=_money_string(row["total_amount"]), currency=currency),
        quantity=_quantity_string(Decimal(str(row["quantity"]))),
        base_unit=str(row["base_unit"]),
    )


def _money_string(value: object) -> str:
    return format(Decimal(str(value)).quantize(MONEY_QUANT), "f")


def _quantity_string(value: Decimal) -> str:
    return format(value.quantize(QUANTITY_QUANT), "f")


def _subtract_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months
    year = value.year
    while month_index <= 0:
        month_index += 12
        year -= 1
    day = min(value.day, _days_in_month(year, month_index))
    return value.replace(year=year, month=month_index, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0):
            return 29
        return 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31
