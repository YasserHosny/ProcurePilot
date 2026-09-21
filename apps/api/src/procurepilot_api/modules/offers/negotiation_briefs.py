"""Deterministic, evidence-linked negotiation brief drafts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal
from uuid import UUID

from procurepilot_api.modules.offers.schemas import (
    BriefItemKind,
    Money,
    NegotiationBriefItem,
    SupplierRiskResult,
)
from procurepilot_api.modules.offers.supplier_iq_v2 import PurchaseOrder

BRIEF_VERSION = "negotiation-brief-v1"
CALCULATION_VERSION = "negotiation-brief-v1"
__all__ = [
    "BRIEF_VERSION",
    "BriefContext",
    "BriefDraft",
    "NegotiationBriefService",
    "build_negotiation_brief",
]


@dataclass(frozen=True)
class BriefBill:
    id: UUID
    status: str
    due_date: date | None
    remaining_balance: Decimal | None
    currency: str | None


@dataclass(frozen=True)
class BriefContext:
    supplier_id: UUID
    as_of: date
    orders: tuple[PurchaseOrder, ...] = ()
    bills: tuple[BriefBill, ...] = ()
    payment_term_source_id: UUID | None = None
    quality_issue_ids: tuple[UUID, ...] = ()
    discrepancy_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class BriefDraft:
    supplier_id: UUID
    snapshot_fingerprint: str
    brief_version: str
    release_posture: Literal["g3_unmet"]
    valid_from: date
    valid_until: date
    items: tuple[NegotiationBriefItem, ...]


_ORDER: tuple[BriefItemKind, ...] = (
    "price_trajectory",
    "alternatives",
    "service_performance",
    "concentration_volume",
    "payment_context",
    "purchase_pattern",
)


def build_negotiation_brief(
    snapshot: SupplierRiskResult,
    context: BriefContext,
) -> BriefDraft:
    """Build at most one deterministic, source-linked point per category."""
    if snapshot.supplier_id != context.supplier_id:
        raise ValueError("snapshot and brief context supplier IDs must match")
    if snapshot.state == "insufficient_data" or snapshot.score is None:
        raise ValueError("insufficient Supplier IQ evidence")
    if snapshot.window_end > context.as_of:
        raise ValueError("snapshot is from the future")

    candidates = [
        _risk_component_item(
            snapshot, "price_drift", "price_trajectory", "negotiationBrief.priceTrajectory.question"
        ),
        _risk_component_item(
            snapshot, "single_source", "alternatives", "negotiationBrief.alternatives.question"
        ),
        _risk_component_item(
            snapshot,
            "reliability",
            "service_performance",
            "negotiationBrief.servicePerformance.question",
        ),
        _concentration_item(snapshot, "negotiationBrief.concentrationVolume.question"),
        _payment_item(context, "negotiationBrief.paymentContext.question"),
        _purchase_pattern_item(context, "negotiationBrief.purchasePattern.question"),
    ]
    available = [item for item in candidates if item is not None]
    available.sort(
        key=lambda item: (
            -(Decimal(item.risk) if item.risk is not None else Decimal("-1")),
            _ORDER.index(item.kind),
        )
    )
    ranked = tuple(item.model_copy(update={"rank": rank}) for rank, item in enumerate(available, 1))
    return BriefDraft(
        supplier_id=snapshot.supplier_id,
        snapshot_fingerprint=snapshot.source_fingerprint,
        brief_version=BRIEF_VERSION,
        release_posture=snapshot.release_posture,
        valid_from=snapshot.window_end,
        valid_until=context.as_of + timedelta(days=1),
        items=ranked,
    )


def _risk_component_item(
    snapshot: SupplierRiskResult,
    component_name: Literal["price_drift", "single_source", "reliability"],
    kind: BriefItemKind,
    question_key: str,
) -> NegotiationBriefItem | None:
    component = snapshot.components[component_name]
    evidence_ids = component.source_ids
    if component.risk is None or not evidence_ids:
        return None
    return NegotiationBriefItem(
        kind=kind,
        rank=1,
        value=_decimal_text(component.value),
        confidence=component.confidence,
        risk=_decimal_text(component.risk),
        valid_from=component.window_start,
        valid_until=component.window_end,
        question_i18n_key=question_key,
        calculation_version=component.calculation_version,
        evidence_ids=evidence_ids,
    )


def _concentration_item(
    snapshot: SupplierRiskResult, question_key: str
) -> NegotiationBriefItem | None:
    component = snapshot.components["concentration"]
    buckets = [bucket for bucket in component.currency_buckets if bucket.share is not None]
    if component.risk is None or not buckets:
        return None
    bucket = max(buckets, key=lambda item: (item.share or Decimal("-1"), item.currency))
    return NegotiationBriefItem(
        kind="concentration_volume",
        rank=1,
        value=_decimal_text(bucket.share),
        amount=Money(amount=_decimal_text(bucket.supplier_spend), currency=bucket.currency),
        confidence=component.confidence,
        risk=_decimal_text(component.risk),
        valid_from=component.window_start,
        valid_until=component.window_end,
        question_i18n_key=question_key,
        calculation_version=component.calculation_version,
        evidence_ids=bucket.source_ids,
    )


def _payment_item(context: BriefContext, question_key: str) -> NegotiationBriefItem | None:
    due_open = [
        bill
        for bill in context.bills
        if bill.status in {"open", "partially_paid"} and bill.due_date is not None
    ]
    overdue = [bill for bill in due_open if bill.due_date < context.as_of]
    if not overdue:
        return None
    currencies = {
        bill.currency
        for bill in overdue
        if bill.remaining_balance is not None and bill.currency is not None
    }
    amount = None
    if len(currencies) == 1:
        currency = next(iter(currencies))
        amount = Money(
            amount=_decimal_text(
                sum(
                    (
                        bill.remaining_balance or Decimal("0")
                        for bill in overdue
                        if bill.currency == currency
                    ),
                    Decimal("0"),
                )
            ),
            currency=currency,
        )
    evidence_ids = tuple(bill.id for bill in overdue)
    return NegotiationBriefItem(
        kind="payment_context",
        rank=1,
        value=_decimal_text(Decimal(len(overdue)) / Decimal(len(due_open))),
        amount=amount,
        confidence="high" if len(due_open) >= 10 else "medium" if len(due_open) >= 3 else "low",
        risk=_decimal_text(Decimal(len(overdue)) / Decimal(len(due_open))),
        valid_from=min(bill.due_date for bill in due_open if bill.due_date is not None),
        valid_until=context.as_of + timedelta(days=1),
        question_i18n_key=question_key,
        calculation_version=CALCULATION_VERSION,
        evidence_ids=evidence_ids,
    )


def _purchase_pattern_item(context: BriefContext, question_key: str) -> NegotiationBriefItem | None:
    dates = sorted({order.ordered_on for order in context.orders})
    if len(dates) < 4:
        return None
    intervals = [(right - left).days for left, right in zip(dates, dates[1:], strict=False)]
    median_days = median(intervals)
    evidence_ids = tuple(order.id for order in context.orders if order.ordered_on in dates)
    return NegotiationBriefItem(
        kind="purchase_pattern",
        rank=1,
        value=_decimal_text(Decimal(str(median_days))),
        confidence="high" if len(dates) >= 10 else "medium",
        risk=None,
        valid_from=dates[0],
        valid_until=dates[-1],
        question_i18n_key=question_key,
        calculation_version=CALCULATION_VERSION,
        evidence_ids=evidence_ids,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.0001")), "f")


class NegotiationBriefService:
    """Pure draft facade; database persistence is added at the API boundary."""

    @staticmethod
    def prepare(snapshot: SupplierRiskResult, context: BriefContext) -> BriefDraft:
        return build_negotiation_brief(snapshot, context)
