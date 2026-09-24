"""Pure retrieval-and-calculation functions for the Grounded Procurement Analyst (R4.2).

Architecture mirrors modules/offers/supplier_iq_v2.py exactly:
- Each function is PURE — it takes a typed input object (already-tenant-scoped records
  supplied by the caller, NOT a database connection) and returns a typed answer or an
  explicit "no grounding data" result.
- No database connections, no bare SQL, no tenant_id looked up here.
  The caller is responsible for scoping all input records to the correct tenant before
  passing them in.  A cross-tenant or unknown identifier therefore resolves to "no
  grounding data" automatically — retrieval.py never trusts an identifier it wasn't
  explicitly handed as pre-scoped input (FR-007).
- Decimal arithmetic throughout; explicit currency on every monetary value.
- No cross-currency aggregation — a mix of currencies is surfaced as a conflict, never
  silently collapsed (FR-004).
- Calculation version pinned to ``CALCULATION_VERSION`` on every answer.
- Replay-determinism: identical inputs at the same calculation version always produce a
  bit-identical result (Constitution Principle II).

Supported FR-002 categories (one pure function per category):
  1. spend_savings           → retrieve_spend_savings()
  2. supplier_performance_risk → retrieve_supplier_performance_risk()
  3. orders_quotations       → retrieve_orders_quotations()
  4. reorder_forecasts       → retrieve_reorder_forecasts()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal
from uuid import UUID

from procurepilot_api.modules.analyst.schemas import (
    AnalystCitationCreate,
    CalculationDetail,
    CitationSourceKind,
    Money,
)

CALCULATION_VERSION: str = "analyst-retrieval-v1"

__all__ = [
    "CALCULATION_VERSION",
    # Input types
    "SpendRecord",
    "SavingRecord",
    "SupplierRiskRecord",
    "OrderRecord",
    "QuotationRecord",
    "ReorderRecord",
    # Input containers
    "SpendSavingsInput",
    "SupplierPerformanceRiskInput",
    "OrdersQuotationsInput",
    "ReorderForecastsInput",
    # Result types
    "AnalystAnswer",
    "NoGroundingData",
    # Public pure functions
    "retrieve_spend_savings",
    "retrieve_supplier_performance_risk",
    "retrieve_orders_quotations",
    "retrieve_reorder_forecasts",
]

# ---------------------------------------------------------------------------
# Shared result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalystAnswer:
    """A grounded answer with calculation and citations.

    ``value`` is the primary Money answer; ``value_text`` is used for non-monetary
    answers (counts, statuses).  At least one of them must be set.
    ``citations`` references the exact source records the calculation used.
    ``calculation`` exposes the inputs, formula, and result for auditability (FR-004).
    ``next_step_url`` is present only when an existing actionable surface applies (FR-003A).
    ``calculation_version`` is always pinned to ``CALCULATION_VERSION``.
    """

    answer_text: str
    calculation: CalculationDetail
    citations: tuple[AnalystCitationCreate, ...]
    calculation_version: str = CALCULATION_VERSION
    value: Money | None = None
    value_text: str | None = None
    next_step_url: str | None = None


@dataclass(frozen=True)
class NoGroundingData:
    """Explicit signal that no tenant records ground an answer (FR-006).

    The reason describes *why* there is no grounding, not a guess at the answer.
    """

    reason: Literal[
        "no_records",
        "currency_conflict",
        "unknown_identifier",
        "unsupported_category",
    ]
    explanation: str
    calculation_version: str = CALCULATION_VERSION


AnalystResult = AnalystAnswer | NoGroundingData


# ---------------------------------------------------------------------------
# Input data-types per category
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpendRecord:
    """One purchase / landed-cost record in the tenant's own data."""

    id: UUID
    source_kind: CitationSourceKind  # purchase_order or landed_cost
    supplier_id: UUID | None
    product_id: UUID | None
    amount: Decimal
    currency: str
    recorded_on: date


@dataclass(frozen=True)
class SavingRecord:
    """One saving record in the tenant's own data."""

    id: UUID
    product_id: UUID | None
    supplier_id: UUID | None
    amount: Decimal
    currency: str
    recorded_on: date


@dataclass(frozen=True)
class SpendSavingsInput:
    """All pre-scoped spend and saving records for this tenant + query."""

    spend_records: tuple[SpendRecord, ...] = field(default_factory=tuple)
    saving_records: tuple[SavingRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SupplierRiskRecord:
    """One supplier scorecard/risk snapshot already scoped to this tenant."""

    id: UUID
    supplier_id: UUID
    supplier_name: str
    risk_level: str | None  # "low", "medium", "high", or None (insufficient)
    risk_score: Decimal | None
    state: str  # "ready", "provisional", "insufficient_data"
    window_end: date
    latest_negotiation_brief_id: UUID | None = None


@dataclass(frozen=True)
class SupplierPerformanceRiskInput:
    """All pre-scoped risk snapshots for this tenant + query."""

    snapshots: tuple[SupplierRiskRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OrderRecord:
    """One purchase order row already scoped to this tenant."""

    id: UUID
    supplier_id: UUID
    status: str
    total_amount: Decimal
    currency: str
    order_date: date
    expected_delivery_date: date | None


@dataclass(frozen=True)
class QuotationRecord:
    """One quotation line row already scoped to this tenant."""

    id: UUID
    supplier_id: UUID | None
    product_id: UUID | None
    unit_price_amount: Decimal
    currency: str
    created_at: date


@dataclass(frozen=True)
class OrdersQuotationsInput:
    """All pre-scoped order and quotation records for this tenant + query."""

    orders: tuple[OrderRecord, ...] = field(default_factory=tuple)
    quotations: tuple[QuotationRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReorderRecord:
    """One reorder proposal row already scoped to this tenant."""

    id: UUID
    product_id: UUID
    proposed_quantity: Decimal
    status: str  # "pending", "approved", "rejected", "cancelled"
    created_at: date
    urgency: str | None


@dataclass(frozen=True)
class ReorderForecastsInput:
    """All pre-scoped reorder proposals for this tenant + query."""

    proposals: tuple[ReorderRecord, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _money(amount: Decimal, currency: str) -> Money:
    with localcontext() as ctx:
        ctx.prec = 28
        rounded = amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Money(amount=format(rounded, "f"), currency=currency)


def _detect_currency_conflict(
    values: list[tuple[Decimal, str]],
) -> str | None:
    """Return conflicting currencies as a description, or None if homogeneous."""
    currencies = {c for _, c in values}
    if len(currencies) > 1:
        return ", ".join(sorted(currencies))
    return None


# ---------------------------------------------------------------------------
# Category 1: Spend and savings
# ---------------------------------------------------------------------------


def retrieve_spend_savings(inputs: SpendSavingsInput) -> AnalystResult:
    """Pure spend+savings retrieval.

    Sums spend and savings amounts per currency.  If multiple currencies are
    present, surfaces the conflict rather than aggregating across currencies
    (FR-004).  Returns NoGroundingData when no records are found.
    """
    spend = list(inputs.spend_records)
    savings = list(inputs.saving_records)

    if not spend and not savings:
        return NoGroundingData(
            reason="no_records",
            explanation=(
                "No spend or savings records are available for this query. "
                "This analyst never guesses when no data exists."
            ),
        )

    # Group by currency — no cross-currency aggregation.
    spend_by_currency: dict[str, list[SpendRecord]] = {}
    for s in spend:
        spend_by_currency.setdefault(s.currency, []).append(s)

    savings_by_currency: dict[str, list[SavingRecord]] = {}
    for s in savings:
        savings_by_currency.setdefault(s.currency, []).append(s)

    all_currencies = set(spend_by_currency) | set(savings_by_currency)
    if len(all_currencies) > 1:
        conflict_str = ", ".join(sorted(all_currencies))
        # Surface both currencies per spec — do not silently pick one.
        per_currency_lines = []
        for ccy in sorted(all_currencies):
            sp_total = sum((r.amount for r in spend_by_currency.get(ccy, [])), Decimal(0))
            sv_total = sum((r.amount for r in savings_by_currency.get(ccy, [])), Decimal(0))
            per_currency_lines.append(
                f"{ccy}: spend {sp_total:,.4f}, savings {sv_total:,.4f}"
            )
        citation_list: list[AnalystCitationCreate] = [
            AnalystCitationCreate(source_kind=r.source_kind, source_id=r.id) for r in spend
        ] + [
            AnalystCitationCreate(source_kind=CitationSourceKind.saving_record, source_id=r.id)
            for r in savings
        ]
        answer_text = (
            f"Records span multiple currencies ({conflict_str}). "
            "No cross-currency aggregation is performed. "
            "Per-currency breakdown: " + "; ".join(per_currency_lines) + "."
        )
        return AnalystAnswer(
            answer_text=answer_text,
            calculation=CalculationDetail(
                inputs=[
                    {
                        "currency": ccy,
                        "record_count": (
                            len(spend_by_currency.get(ccy, []))
                            + len(savings_by_currency.get(ccy, []))
                        ),
                    }
                    for ccy in sorted(all_currencies)
                ],
                formula="per-currency sum only — no cross-currency aggregation",
            ),
            citations=tuple(citation_list),
            next_step_url="/reports",
        )

    # Single currency path
    ccy = next(iter(all_currencies)) if all_currencies else "XXX"
    total_spend = sum((r.amount for r in spend), Decimal(0))
    total_savings = sum((r.amount for r in savings), Decimal(0))

    citations = tuple(
        [
            AnalystCitationCreate(source_kind=r.source_kind, source_id=r.id)
            for r in spend
        ]
        + [
            AnalystCitationCreate(source_kind=CitationSourceKind.saving_record, source_id=r.id)
            for r in savings
        ]
    )
    spend_str = format(total_spend.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ",.2f")
    savings_str = format(total_savings.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ",.2f")
    answer_text = (
        f"Total spend: {ccy} {spend_str} across {len(spend)} record(s). "
        f"Total savings: {ccy} {savings_str} across {len(savings)} record(s)."
    )
    return AnalystAnswer(
        answer_text=answer_text,
        value=_money(total_spend, ccy),
        calculation=CalculationDetail(
            inputs=[
                {"label": "spend records", "count": len(spend), "currency": ccy},
                {"label": "savings records", "count": len(savings), "currency": ccy},
            ],
            formula="sum of all spend amounts; sum of all savings amounts",
            result=_money(total_spend, ccy),
        ),
        citations=citations,
        next_step_url="/reports",
    )


# ---------------------------------------------------------------------------
# Category 2: Supplier performance and risk
# ---------------------------------------------------------------------------


def retrieve_supplier_performance_risk(
    inputs: SupplierPerformanceRiskInput,
) -> AnalystResult:
    """Pure supplier risk retrieval.

    Returns the most-recent snapshot per supplier.  Surfaces conflicting
    risk levels (e.g. two snapshots for the same supplier disagree) instead of
    silently picking one.  Returns NoGroundingData when no snapshots exist.
    """
    snapshots = list(inputs.snapshots)

    if not snapshots:
        return NoGroundingData(
            reason="no_records",
            explanation=(
                "No supplier scorecard or risk snapshots are available for this query. "
                "This analyst never guesses when no data exists."
            ),
        )

    # Group by supplier, pick the most-recent snapshot.
    by_supplier: dict[UUID, list[SupplierRiskRecord]] = {}
    for s in snapshots:
        by_supplier.setdefault(s.supplier_id, []).append(s)

    summary_lines: list[str] = []
    citations: list[AnalystCitationCreate] = []
    conflicting = False

    for _supplier_id, records in sorted(by_supplier.items(), key=lambda kv: str(kv[0])):
        records_sorted = sorted(records, key=lambda r: r.window_end, reverse=True)
        latest = records_sorted[0]
        citations.append(
            AnalystCitationCreate(
                source_kind=CitationSourceKind.supplier_scorecard_snapshot,
                source_id=latest.id,
            )
        )
        if len(records_sorted) > 1:
            risk_levels = {r.risk_level for r in records_sorted}
            if len(risk_levels) > 1:
                conflicting = True
                level_str = ", ".join(str(lvl) for lvl in sorted(risk_levels, key=str))
                summary_lines.append(
                    f"{latest.supplier_name}: conflicting risk levels across snapshots "
                    f"({level_str}) — both are reported, not resolved"
                )
                for r in records_sorted[1:]:
                    citations.append(
                        AnalystCitationCreate(
                            source_kind=CitationSourceKind.supplier_scorecard_snapshot,
                            source_id=r.id,
                        )
                    )
                continue
        risk_desc = latest.risk_level if latest.risk_level else f"state={latest.state}"
        summary_lines.append(
            f"{latest.supplier_name}: risk_level={risk_desc}, "
            f"score={latest.risk_score}, as-of={latest.window_end}"
        )

    if conflicting:
        answer_text = (
            "Conflicting risk records found — both are surfaced below (not resolved). "
            + " | ".join(summary_lines)
        )
    else:
        answer_text = "Supplier risk summary: " + " | ".join(summary_lines) + "."

    # FR-003A: link to the first cited supplier's existing negotiation brief, in the
    # same supplier order already used above. Never fabricate a brief that doesn't exist.
    next_step_url: str | None = None
    for _supplier_id, records in sorted(by_supplier.items(), key=lambda kv: str(kv[0])):
        latest = sorted(records, key=lambda r: r.window_end, reverse=True)[0]
        if latest.latest_negotiation_brief_id is not None:
            next_step_url = f"/negotiation-briefs/{latest.latest_negotiation_brief_id}"
            break

    return AnalystAnswer(
        answer_text=answer_text,
        calculation=CalculationDetail(
            inputs=[
                {
                    "supplier": str(r.supplier_id),
                    "name": r.supplier_name,
                    "risk_level": str(r.risk_level),
                    "score": str(r.risk_score),
                    "window_end": r.window_end.isoformat(),
                }
                for r in snapshots
            ],
            formula=(
                "most-recent snapshot per supplier; "
                "conflict surfaced when risk levels disagree"
            ),
        ),
        citations=tuple(citations),
        next_step_url=next_step_url,
    )


# ---------------------------------------------------------------------------
# Category 3: Orders and quotations
# ---------------------------------------------------------------------------


def retrieve_orders_quotations(inputs: OrdersQuotationsInput) -> AnalystResult:
    """Pure order+quotation retrieval.

    Summarises order status counts and quotation line price range.
    Currency conflicts (multiple currencies among quotations) are surfaced
    per FR-004 rather than aggregated.
    """
    orders = list(inputs.orders)
    quotations = list(inputs.quotations)

    if not orders and not quotations:
        return NoGroundingData(
            reason="no_records",
            explanation=(
                "No purchase orders or quotation lines are available for this query. "
                "This analyst never guesses when no data exists."
            ),
        )

    citations: list[AnalystCitationCreate] = [
        AnalystCitationCreate(source_kind=CitationSourceKind.purchase_order, source_id=o.id)
        for o in orders
    ] + [
        AnalystCitationCreate(source_kind=CitationSourceKind.quotation_line, source_id=q.id)
        for q in quotations
    ]

    # Order status distribution
    status_counts: dict[str, int] = {}
    order_currencies: dict[str, list[Decimal]] = {}
    for o in orders:
        status_counts[o.status] = status_counts.get(o.status, 0) + 1
        order_currencies.setdefault(o.currency, []).append(o.total_amount)

    order_currency_conflict = _detect_currency_conflict(
        [(amt, ccy) for ccy, amounts in order_currencies.items() for amt in amounts]
    )

    # Quotation line price range
    quotation_currencies: dict[str, list[Decimal]] = {}
    for q in quotations:
        quotation_currencies.setdefault(q.currency, []).append(q.unit_price_amount)

    quotation_currency_conflict = _detect_currency_conflict(
        [(amt, ccy) for ccy, amounts in quotation_currencies.items() for amt in amounts]
    )

    lines: list[str] = []
    if orders:
        status_str = ", ".join(f"{k}:{v}" for k, v in sorted(status_counts.items()))
        lines.append(f"{len(orders)} order(s): statuses [{status_str}]")
        if order_currency_conflict:
            lines.append(f"(order currencies conflict: {order_currency_conflict})")
        else:
            for ccy, amounts in sorted(order_currencies.items()):
                total = sum(amounts, Decimal(0))
                lines.append(
                    f"  order total {ccy} "
                    f"{format(total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), ',.2f')}"
                )

    if quotations:
        lines.append(f"{len(quotations)} quotation line(s)")
        if quotation_currency_conflict:
            lines.append(f"(quotation currencies conflict: {quotation_currency_conflict})")
        else:
            for ccy, prices in sorted(quotation_currencies.items()):
                lo = min(prices)
                hi = max(prices)
                lines.append(
                    f"  unit price range {ccy} "
                    f"{format(lo.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), ',.2f')}"
                    f"–"
                    f"{format(hi.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), ',.2f')}"
                )

    answer_text = "Order and quotation summary: " + "; ".join(lines) + "."
    return AnalystAnswer(
        answer_text=answer_text,
        calculation=CalculationDetail(
            inputs=[
                {"order_count": len(orders), "quotation_count": len(quotations)},
                {"status_distribution": status_counts},
            ],
            formula=(
                "order status count distribution; "
                "quotation unit-price range per currency (no cross-currency aggregation)"
            ),
        ),
        citations=tuple(citations),
    )


# ---------------------------------------------------------------------------
# Category 4: Reorder forecasts
# ---------------------------------------------------------------------------


def retrieve_reorder_forecasts(inputs: ReorderForecastsInput) -> AnalystResult:
    """Pure reorder forecast retrieval.

    Summarises pending and approved reorder proposals.  Returns NoGroundingData
    when no proposals exist.
    """
    proposals = list(inputs.proposals)

    if not proposals:
        return NoGroundingData(
            reason="no_records",
            explanation=(
                "No reorder proposals are available for this query. "
                "This analyst never guesses when no data exists."
            ),
        )

    status_counts: dict[str, int] = {}
    for p in proposals:
        status_counts[p.status] = status_counts.get(p.status, 0) + 1

    citations = tuple(
        AnalystCitationCreate(source_kind=CitationSourceKind.reorder_proposal, source_id=p.id)
        for p in proposals
    )

    status_str = ", ".join(f"{k}:{v}" for k, v in sorted(status_counts.items()))
    urgent_count = sum(1 for p in proposals if p.urgency and p.urgency != "normal")
    answer_text = (
        f"{len(proposals)} reorder proposal(s) found. "
        f"Status breakdown: [{status_str}]. "
        f"Urgent: {urgent_count}."
    )

    return AnalystAnswer(
        answer_text=answer_text,
        calculation=CalculationDetail(
            inputs=[
                {
                    "proposal_id": str(p.id),
                    "product_id": str(p.product_id),
                    "status": p.status,
                    "proposed_quantity": str(p.proposed_quantity),
                    "urgency": p.urgency,
                }
                for p in proposals
            ],
            formula="status distribution and urgency count across all proposals",
        ),
        citations=citations,
        next_step_url="/forecasting",
    )
