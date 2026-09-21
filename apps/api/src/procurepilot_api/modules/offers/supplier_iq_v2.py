"""Pure Supplier IQ v2, over tenant-scoped source projections supplied by the caller.

Windows are [start, split) and [split, end). End is also the as-of date for
alternative validity. Reliability means all PO lines completed by expected date;
late receipts never repair on-time performance. Count confidence uses the weakest
period/bucket supporting a component, and price coverage counts distinct products.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from statistics import median
from typing import Literal
from uuid import UUID

from procurepilot_api.modules.offers.schemas import (
    RiskCurrencyBucket,
    RiskPriceComparison,
    SupplierRiskComponentV2,
    SupplierRiskResult,
)

SCORECARD_VERSION = "supplier-scorecard-v2"
RISK_VERSION = "supplier-risk-v2"
__all__ = [
    "RISK_VERSION",
    "SCORECARD_VERSION",
    "SupplierRiskInput",
    "SupplierRiskResult",
    "calculate_supplier_risk",
    "source_fingerprint",
]

ZERO = Decimal(0)
ONE = Decimal(1)
QUALIFYING = frozenset({"submitted", "confirmed", "partially_received", "received", "closed"})
RELIABILITY_EXCLUDED = frozenset({"draft", "cancelled"})
WEIGHTS = dict(
    concentration=Decimal(".30"),
    price_drift=Decimal(".25"),
    reliability=Decimal(".25"),
    single_source=Decimal(".20"),
)


def _require_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


@dataclass(frozen=True)
class OrderLine:
    id: UUID
    product_id: UUID
    base_unit: str
    quantity: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "quantity")


@dataclass(frozen=True)
class PurchaseOrder:
    id: UUID
    supplier_id: UUID
    ordered_on: date
    expected_delivery_date: date | None
    status: str
    amount: Decimal
    currency: str
    lines: tuple[OrderLine, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        _require_decimal(self.amount, "amount")
        line_ids = [line.id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Duplicate order line IDs")


@dataclass(frozen=True)
class ReceiptLine:
    id: UUID
    purchase_order_id: UUID
    purchase_order_line_id: UUID
    quantity: Decimal
    received_at: datetime

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "quantity")


@dataclass(frozen=True)
class Price:
    id: UUID
    supplier_id: UUID
    product_id: UUID
    base_unit: str
    currency: str
    unit_price: Decimal
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_decimal(self.unit_price, "unit_price")


@dataclass(frozen=True)
class Alternative(Price):
    valid_from: date
    valid_to: date | None = None
    active: bool = True


@dataclass(frozen=True, kw_only=True)
class SupplierRiskInput:
    supplier_id: UUID
    window_end: date
    window_start: date | None = None
    split_date: date | None = None
    purchase_orders: tuple[PurchaseOrder, ...] = ()
    receipts: tuple[ReceiptLine, ...] = ()
    prices: tuple[Price, ...] = ()
    alternatives: tuple[Alternative, ...] = ()

    def __post_init__(self) -> None:
        start = self.window_start or self.window_end - timedelta(days=180)
        duration = (self.window_end - start).days
        split = self.split_date or start + timedelta(days=duration // 2)
        if duration <= 0 or duration % 2 or split - start != self.window_end - split:
            raise ValueError("Evidence periods must be positive and equal")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "split_date", split)
        for field in ("purchase_orders", "receipts", "prices", "alternatives"):
            rows = tuple(getattr(self, field))
            if len({row.id for row in rows}) != len(rows):
                raise ValueError(f"Duplicate source IDs in {field}")
            object.__setattr__(self, field, tuple(sorted(rows, key=lambda row: row.id)))


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite source value")
        return (
            "0"
            if value == 0
            else format(value, "f").rstrip("0").rstrip(".")
            if "." in format(value, "f")
            else format(value, "f")
        )
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        items = [_canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def source_fingerprint(payload: SupplierRiskInput) -> str:
    source = {
        "scorecard_version": SCORECARD_VERSION,
        "risk_version": RISK_VERSION,
        "input": asdict(payload),
    }
    return hashlib.sha256(
        json.dumps(_canonical(source), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _confidence(count: int) -> Literal["low", "medium", "high"]:
    return "high" if count >= 10 else "medium" if count >= 3 else "low"


def _clamp(value: Decimal) -> Decimal:
    return min(ONE, max(ZERO, value))


def _level(value: Decimal | None) -> Literal["low", "medium", "high"] | None:
    if value is None:
        return None
    return "low" if value < Decimal(".35") else "medium" if value < Decimal(".65") else "high"


def _component(
    p: SupplierRiskInput,
    *,
    count: int,
    value: Decimal | None,
    risk: Decimal | None,
    ids: list[UUID],
    excluded: Counter[str],
    products: int = 0,
) -> SupplierRiskComponentV2:
    assert p.window_start is not None and p.split_date is not None
    return SupplierRiskComponentV2(
        value=value,
        risk=risk if count >= 3 else None,
        sample_count=count,
        product_count=products,
        confidence=_confidence(count),
        insufficient_evidence=count < 3 or risk is None,
        excluded_counts=dict(sorted(excluded.items())),
        source_ids=sorted(set(ids)),
        window_start=p.window_start,
        split_date=p.split_date,
        window_end=p.window_end,
        calculation_version=RISK_VERSION,
    )


def _concentration(p: SupplierRiskInput) -> SupplierRiskComponentV2:
    groups: dict[str, list[PurchaseOrder]] = defaultdict(list)
    excluded: Counter[str] = Counter()
    for order in p.purchase_orders:
        if order.status not in QUALIFYING:
            excluded["status"] += 1
        elif not p.window_start <= order.ordered_on < p.window_end:
            excluded["outside_window"] += 1
        elif order.amount < 0:
            excluded["negative_amount"] += 1
        else:
            groups[order.currency].append(order)
    buckets = []
    for currency, rows in sorted(groups.items()):
        own = [row for row in rows if row.supplier_id == p.supplier_id]
        total = sum((row.amount for row in rows), ZERO)
        spend = sum((row.amount for row in own), ZERO)
        share = spend / total if total > 0 and len(rows) >= 3 and own else None
        if share is None:
            excluded["insufficient_currency_bucket"] += 1
        buckets.append(
            RiskCurrencyBucket(
                currency=currency,
                supplier_spend=spend,
                tenant_spend=total,
                sample_count=len(rows),
                share=share,
                source_ids=sorted(row.id for row in rows),
            )
        )
    valid = [b for b in buckets if b.share is not None]
    risk = max((b.share for b in valid), default=None)
    result = _component(
        p,
        count=min((b.sample_count for b in valid), default=0),
        value=risk,
        risk=risk,
        ids=[i for b in buckets for i in b.source_ids],
        excluded=excluded,
    )
    return result.model_copy(update={"currency_buckets": tuple(buckets)})


def _prices(p: SupplierRiskInput) -> SupplierRiskComponentV2:
    groups: dict[tuple[UUID, str, str], tuple[list[Price], list[Price]]] = {}
    excluded: Counter[str] = Counter()
    for row in p.prices:
        day = _utc(row.recorded_at).date()
        if row.supplier_id != p.supplier_id:
            excluded["other_supplier"] += 1
        elif not p.window_start <= day < p.window_end:
            excluded["outside_window"] += 1
        elif row.unit_price < 0:
            excluded["negative_price"] += 1
        else:
            pair = groups.setdefault((row.product_id, row.base_unit, row.currency), ([], []))
            pair[int(day >= p.split_date)].append(row)
    comparisons = []
    for (product, unit, currency), (baseline, current) in sorted(groups.items()):
        if not baseline or not current:
            excluded["unpaired_group"] += 1
            continue
        before = median([row.unit_price for row in baseline])
        after = median([row.unit_price for row in current])
        if before == 0:
            excluded["zero_baseline"] += 1
            continue
        comparisons.append(
            RiskPriceComparison(
                product_id=product,
                base_unit=unit,
                currency=currency,
                baseline_median=before,
                current_median=after,
                drift=(after - before) / before,
                source_ids=sorted(row.id for row in baseline + current),
            )
        )
    products = len({c.product_id for c in comparisons})
    drift = median([c.drift for c in comparisons]) if comparisons else None
    risk = (
        _clamp(max(drift, ZERO) / Decimal(".20")) if drift is not None and products >= 3 else None
    )
    result = _component(
        p,
        count=len(comparisons),
        products=products,
        value=drift,
        risk=risk,
        ids=[i for c in comparisons for i in c.source_ids],
        excluded=excluded,
    )
    return result.model_copy(update={"price_comparisons": tuple(comparisons)})


def _reliability(p: SupplierRiskInput) -> SupplierRiskComponentV2:
    excluded: Counter[str] = Counter()
    outcomes: tuple[list[bool], list[bool]] = ([], [])
    ids: list[UUID] = []
    receipts: dict[UUID, list[ReceiptLine]] = defaultdict(list)
    for receipt in p.receipts:
        receipts[receipt.purchase_order_id].append(receipt)
    for order in p.purchase_orders:
        due = order.expected_delivery_date
        if order.supplier_id != p.supplier_id:
            continue
        if order.status in RELIABILITY_EXCLUDED:
            excluded["status"] += 1
            continue
        if due is None:
            excluded["no_expected_date"] += 1
            continue
        if due >= p.window_end:
            excluded["not_yet_due"] += 1
            continue
        if due < p.window_start:
            excluded["outside_window"] += 1
            continue
        if not order.lines or any(line.quantity <= 0 for line in order.lines):
            excluded["invalid_order_lines"] += 1
            continue
        quantities: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
        line_ids = {line.id for line in order.lines}
        for receipt in receipts[order.id]:
            if receipt.purchase_order_line_id not in line_ids:
                excluded["unknown_receipt_line"] += 1
            elif receipt.quantity < 0:
                excluded["negative_receipt"] += 1
            elif _utc(receipt.received_at).date() >= p.window_end:
                excluded["future_receipt"] += 1
            else:
                ids.append(receipt.id)
                if _utc(receipt.received_at).date() <= due:
                    quantities[receipt.purchase_order_line_id] += receipt.quantity
                else:
                    excluded["late_receipt"] += 1
        outcomes[int(due >= p.split_date)].append(
            all(quantities[line.id] >= line.quantity for line in order.lines)
        )
        ids.append(order.id)
    baseline, current = outcomes
    before = Decimal(sum(baseline)) / Decimal(len(baseline)) if len(baseline) >= 3 else None
    after = Decimal(sum(current)) / Decimal(len(current)) if len(current) >= 3 else None
    risk = None
    if after is not None:
        decay = _clamp((before - after) / Decimal(".25")) if before is not None else ZERO
        risk = max(ONE - after, decay)
    count = min(len(baseline), len(current)) if before is not None else len(current)
    result = _component(p, count=count, value=after, risk=risk, ids=ids, excluded=excluded)
    return result.model_copy(
        update={
            "baseline_count": len(baseline),
            "current_count": len(current),
            "baseline_reliability": before,
            "current_reliability": after,
        }
    )


def _single_source(p: SupplierRiskInput) -> SupplierRiskComponentV2:
    purchased: dict[UUID, set[tuple[str, str]]] = defaultdict(set)
    ids: list[UUID] = []
    excluded: Counter[str] = Counter()
    for order in p.purchase_orders:
        if order.supplier_id != p.supplier_id:
            continue
        if (
            order.status in RELIABILITY_EXCLUDED
            or not p.window_start <= order.ordered_on < p.window_end
        ):
            excluded["nonqualifying_order"] += 1
            continue
        for line in order.lines:
            if line.quantity <= 0:
                excluded["nonpositive_quantity"] += 1
                continue
            purchased[line.product_id].add((line.base_unit, order.currency))
            ids.extend([order.id, line.product_id])
    available: set[tuple[UUID, str, str]] = set()
    for row in p.alternatives:
        if row.supplier_id == p.supplier_id or not row.active:
            excluded["inactive_or_same_supplier"] += 1
        elif (
            _utc(row.recorded_at).date() < p.window_start
            or _utc(row.recorded_at).date() >= p.window_end
            or row.valid_from > p.window_end
            or (row.valid_to is not None and row.valid_to <= p.window_end)
        ):
            excluded["invalid_observation"] += 1
        elif row.unit_price < 0:
            excluded["negative_price"] += 1
        elif (row.base_unit, row.currency) not in purchased.get(row.product_id, set()):
            excluded["incompatible_product_unit_currency"] += 1
        else:
            available.add((row.product_id, row.base_unit, row.currency))
            ids.append(row.id)
    products_with_alternatives = {product for product, _unit, _currency in available}
    exposed = sum(product not in products_with_alternatives for product in purchased)
    count = len(purchased)
    value = Decimal(exposed) / Decimal(count) if count else None
    result = _component(
        p, count=count, products=count, value=value, risk=value, ids=ids, excluded=excluded
    )
    return result.model_copy(update={"numerator": Decimal(exposed), "denominator": Decimal(count)})


def _calculate_supplier_risk(payload: SupplierRiskInput) -> SupplierRiskResult:
    p = payload
    fingerprint = source_fingerprint(p)
    components = dict(
        concentration=_concentration(p),
        price_drift=_prices(p),
        reliability=_reliability(p),
        single_source=_single_source(p),
    )
    available = {key: value for key, value in components.items() if value.risk is not None}
    total_weight = sum((WEIGHTS[key] for key in available), ZERO)
    weights = {key: WEIGHTS[key] / total_weight for key in available} if len(available) >= 3 else {}
    # Divide once to avoid rounding each weighted contribution during renormalization.
    score = (
        (
            sum((component.risk * WEIGHTS[key] for key, component in available.items()), ZERO)
            / total_weight
        )
        if weights
        else None
    )
    dates = [
        o.ordered_on
        for o in p.purchase_orders
        if (
            o.supplier_id == p.supplier_id
            and o.status in QUALIFYING
            and o.ordered_on < p.window_end
            and o.amount >= 0
        )
    ]
    dates += [
        _utc(row.recorded_at).date()
        for row in p.prices
        if (
            row.supplier_id == p.supplier_id
            and _utc(row.recorded_at).date() < p.window_end
            and row.unit_price >= 0
        )
    ]
    history = (p.window_end - min(dates)).days if dates else 0
    confidence = (
        "low"
        if score is None
        else "medium"
        if any(c.confidence != "high" for c in available.values())
        else "high"
    )
    state = (
        "insufficient_data"
        if score is None
        else "ready"
        if len(available) == 4 and confidence == "high" and history >= 180
        else "provisional"
    )
    return SupplierRiskResult(
        supplier_id=p.supplier_id,
        components=components,
        weights=weights,
        score=score,
        risk_level=_level(score),
        confidence=confidence,
        state=state,
        window_start=p.window_start,
        split_date=p.split_date,
        window_end=p.window_end,
        observed_history_days=history,
        scorecard_version=SCORECARD_VERSION,
        risk_version=RISK_VERSION,
        source_fingerprint=fingerprint,
    )


def calculate_supplier_risk(payload: SupplierRiskInput) -> SupplierRiskResult:
    with localcontext() as context:
        context.prec = 28
        return _calculate_supplier_risk(payload)
