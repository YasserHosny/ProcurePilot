from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.alerts.fingerprints import (
    alert_fingerprint,
    decimal_anomaly_recurrence_key,
    delivery_cost_recurrence_key,
    duplicate_line_recurrence_key,
    price_spike_recurrence_key,
    supplier_quality_recurrence_key,
)
from procurepilot_api.modules.alerts.schemas import Alert
from procurepilot_api.modules.offers.service import OfferService, _authenticated_db


class AlertConditionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._offers = OfferService(self._settings)

    def live_alerts(self, *, member: CurrentMember, kind: str | None = None) -> list[Alert]:
        now = datetime.now(UTC)
        alerts: list[Alert] = []
        for product in _active_products(self._settings, member):
            product_id = UUID(str(product["id"]))
            compare = self._offers.compare_offers(
                member=member,
                product_id=product_id,
                quantity=Decimal("1.000000"),
            )
            if kind in {None, "recommended_price_expiring"}:
                alerts.extend(_expiring_alerts(member, compare, now))
            if kind in {None, "preferred_supplier_offer_disappeared"}:
                alerts.extend(
                    _preferred_disappeared_alerts(self._settings, member, product, compare, now)
                )
            if kind in {None, "price_swing"}:
                alerts.extend(_price_swing_alerts(self._offers, member, compare, now))
            if kind in {None, "price_spike"}:
                alerts.extend(_price_spike_alerts(self._offers, member, compare, now))
            if kind in {None, "likely_duplicate_quotation_line"}:
                alerts.extend(_duplicate_line_alerts(member, compare, now))
            if kind in {None, "decimal_or_quantity_anomaly"}:
                alerts.extend(_decimal_anomaly_alerts(self._offers, member, compare, now))
            if kind in {None, "delivery_cost_anomaly"}:
                alerts.extend(_delivery_cost_alerts(self._settings, member, compare, now))
            if kind in {None, "supplier_quality_trend_change"}:
                alerts.extend(_supplier_quality_alerts(self._settings, member, compare, now))
        return sorted(
            alerts,
            key=lambda alert: (alert.kind, str(alert.workspace_product_id), alert.id),
        )


def get_alert_condition_service() -> AlertConditionService:
    return AlertConditionService()


def _active_products(settings: Settings, member: CurrentMember) -> list[dict[str, object]]:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, tenant_name, preferred_supplier_id
                from workspace_product
                where status = 'active'
                order by tenant_name, id
                limit 100
                """
            )
            return [dict(row) for row in cur.fetchall()]


def _expiring_alerts(member: CurrentMember, compare: object, now: datetime) -> list[Alert]:
    recommendation = compare.recommendation
    if recommendation is None or recommendation.valid_to is None:
        return []
    if not (now <= recommendation.valid_to <= now + timedelta(days=7)):
        return []
    offer = next(
        offer for offer in compare.offers if offer.id == recommendation.recommended_offer_id
    )
    recurrence_key = f"{offer.id}:{recommendation.valid_to.isoformat()}"
    return [
        Alert(
            id=alert_fingerprint(
                tenant_id=member.tenant_id,
                kind="recommended_price_expiring",
                product_id=compare.product.id,
                supplier_id=offer.supplier_id,
                recurrence_key=recurrence_key,
            ),
            kind="recommended_price_expiring",
            workspace_product_id=compare.product.id,
            supplier_id=offer.supplier_id,
            severity="warning",
            action="compare_product",
            evidence={
                "landed_cost_id": str(offer.id),
                "valid_to": recommendation.valid_to.isoformat(),
                "recommended_offer_id": str(recommendation.recommended_offer_id),
            },
            created_from_current_data_at=now,
            dismissed=False,
        )
    ]


def _preferred_disappeared_alerts(
    settings: Settings,
    member: CurrentMember,
    product: dict[str, object],
    compare: object,
    now: datetime,
) -> list[Alert]:
    preferred = product.get("preferred_supplier_id")
    if preferred is None:
        return []
    preferred_id = UUID(str(preferred))
    current_supplier_ids = {offer.supplier_id for offer in compare.offers if not offer.is_expired}
    if preferred_id in current_supplier_ids:
        return []
    if not _has_historical_offer(settings, member, compare.product.id, preferred_id):
        return []
    latest_non_preferred = sorted(str(offer.id) for offer in compare.offers if not offer.is_expired)
    recurrence_key = f"{preferred_id}:{','.join(latest_non_preferred)}"
    return [
        Alert(
            id=alert_fingerprint(
                tenant_id=member.tenant_id,
                kind="preferred_supplier_offer_disappeared",
                product_id=compare.product.id,
                supplier_id=preferred_id,
                recurrence_key=recurrence_key,
            ),
            kind="preferred_supplier_offer_disappeared",
            workspace_product_id=compare.product.id,
            supplier_id=preferred_id,
            severity="warning",
            action="review_supplier",
            evidence={
                "preferred_supplier_id": str(preferred_id),
                "current_offer_ids": latest_non_preferred,
            },
            created_from_current_data_at=now,
            dismissed=False,
        )
    ]


def _price_swing_alerts(
    offers: OfferService,
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    recommendation = compare.recommendation
    if recommendation is None:
        return []
    offer = next(
        offer for offer in compare.offers if offer.id == recommendation.recommended_offer_id
    )
    history = offers.price_history(member=member, product_id=compare.product.id, window_months=6)
    window_metric = history.summary.average_paid_rolling_window
    if window_metric is None or len(window_metric.source_landed_cost_ids) < 2:
        return []
    average = Decimal(window_metric.value.amount)
    current = Decimal(offer.normalised_unit_price.amount)
    if average == 0:
        return []
    swing = ((current - average) / average).copy_abs()
    if swing < Decimal("0.15"):
        return []
    signed = ((current - average) / average * Decimal("100")).quantize(Decimal("0.01"))
    recurrence_key = f"{offer.id}:{signed}"
    return [
        Alert(
            id=alert_fingerprint(
                tenant_id=member.tenant_id,
                kind="price_swing",
                product_id=compare.product.id,
                supplier_id=offer.supplier_id,
                recurrence_key=recurrence_key,
            ),
            kind="price_swing",
            workspace_product_id=compare.product.id,
            supplier_id=offer.supplier_id,
            severity="critical" if signed > 0 else "info",
            action="view_price_history",
            evidence={
                "current_landed_cost_id": str(offer.id),
                "current_normalised_unit_price": offer.normalised_unit_price.model_dump(
                    mode="json"
                ),
                "rolling_average": window_metric.value.model_dump(mode="json"),
                "swing_percentage": format(signed, "f"),
            },
            created_from_current_data_at=now,
            dismissed=False,
        )
    ]


def _has_historical_offer(
    settings: Settings,
    member: CurrentMember,
    product_id: UUID,
    supplier_id: UUID,
) -> bool:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select lc.id
                from match_decision md
                join landed_cost lc on lc.match_decision_id = md.id
                join quotation_line ql on ql.id = lc.quotation_line_id
                join quotation q on q.id = ql.quotation_id
                where md.matched_workspace_product_id = %s
                  and q.supplier_id = %s
                limit 1
                """,
                (product_id, supplier_id),
            )
            return cur.fetchone() is not None


def _price_spike_alerts(
    offers: OfferService,
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    recommendation = getattr(compare, "recommendation", None)
    if recommendation is None:
        return []
    offer = next(
        (o for o in compare.offers if o.id == recommendation.recommended_offer_id),
        None,
    )
    if offer is None:
        return []
    history = offers.price_history(member=member, product_id=compare.product.id, window_months=6)
    window_metric = history.summary.average_paid_rolling_window
    if window_metric is None or len(window_metric.source_landed_cost_ids) < 2:
        return []
    average = Decimal(window_metric.value.amount)
    current = Decimal(offer.normalised_unit_price.amount)
    if average <= 0:
        return []
    spike = (current - average) / average
    if spike < Decimal("0.20"):
        return []
    spike_pct = (spike * Decimal("100")).quantize(Decimal("0.01"))
    spike_str = format(spike_pct, "f")
    recurrence_key = price_spike_recurrence_key(offer.id, spike_str)
    sample_count = len(window_metric.source_landed_cost_ids)
    confidence: Literal["high", "medium", "low"] = "high" if sample_count >= 5 else "medium"
    severity: Literal["warning", "critical"] = "critical" if spike >= Decimal("0.35") else "warning"
    return [
        Alert(
            id=alert_fingerprint(
                tenant_id=member.tenant_id,
                kind="price_spike",
                product_id=compare.product.id,
                supplier_id=offer.supplier_id,
                recurrence_key=recurrence_key,
            ),
            kind="price_spike",
            workspace_product_id=compare.product.id,
            supplier_id=offer.supplier_id,
            severity=severity,
            confidence=confidence,
            action="view_price_history",
            evidence={
                "landed_cost_id": str(offer.id),
                "current_normalised_unit_price": offer.normalised_unit_price.model_dump(
                    mode="json"
                ),
                "rolling_average": window_metric.value.model_dump(mode="json"),
                "spike_percentage": spike_str,
                "sample_count": sample_count,
            },
            valid_until=offer.valid_to,
            created_from_current_data_at=now,
            dismissed=False,
        )
    ]


def _duplicate_line_alerts(
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    alerts: list[Alert] = []
    active_offers = [o for o in compare.offers if not getattr(o, "is_expired", False)]
    by_supplier: dict[UUID, list[object]] = {}
    for o in active_offers:
        by_supplier.setdefault(o.supplier_id, []).append(o)
    for supplier_id, supplier_offers in by_supplier.items():
        if len(supplier_offers) < 2:
            continue
        for i in range(len(supplier_offers)):
            for j in range(i + 1, len(supplier_offers)):
                o1, o2 = supplier_offers[i], supplier_offers[j]
                if (
                    o1.normalised_unit_price.amount == o2.normalised_unit_price.amount
                    and o1.normalised_unit_price.currency == o2.normalised_unit_price.currency
                ):
                    first, second = sorted([o1, o2], key=lambda o: str(o.id))
                    recurrence_key = duplicate_line_recurrence_key(
                        first.quotation_line_id, second.quotation_line_id
                    )
                    identical_quantity = first.requested_quantity == second.requested_quantity
                    confidence: Literal["high", "medium", "low"] = (
                        "high" if identical_quantity else "medium"
                    )
                    valid_candidates = [
                        d for d in (first.valid_to, second.valid_to) if d is not None
                    ]
                    valid_until = min(valid_candidates) if valid_candidates else None
                    alerts.append(
                        Alert(
                            id=alert_fingerprint(
                                tenant_id=member.tenant_id,
                                kind="likely_duplicate_quotation_line",
                                product_id=compare.product.id,
                                supplier_id=supplier_id,
                                recurrence_key=recurrence_key,
                            ),
                            kind="likely_duplicate_quotation_line",
                            workspace_product_id=compare.product.id,
                            supplier_id=supplier_id,
                            severity="warning",
                            confidence=confidence,
                            action="review_quotation",
                            evidence={
                                "quotation_line_id_1": str(first.quotation_line_id),
                                "quotation_line_id_2": str(second.quotation_line_id),
                                "landed_cost_id_1": str(first.id),
                                "landed_cost_id_2": str(second.id),
                                "unit_price": first.normalised_unit_price.model_dump(mode="json"),
                                "requested_quantity_1": str(first.requested_quantity),
                                "requested_quantity_2": str(second.requested_quantity),
                            },
                            valid_until=valid_until,
                            created_from_current_data_at=now,
                            dismissed=False,
                        )
                    )
    return alerts


def _decimal_anomaly_alerts(
    offers: OfferService,
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    history = offers.price_history(member=member, product_id=compare.product.id, window_months=6)
    window_metric = history.summary.average_paid_rolling_window
    if window_metric is None or len(window_metric.source_landed_cost_ids) < 1:
        return []
    baseline = Decimal(window_metric.value.amount)
    if baseline <= 0:
        return []
    alerts: list[Alert] = []
    sample_count = len(window_metric.source_landed_cost_ids)
    for offer in compare.offers:
        if getattr(offer, "is_expired", False):
            continue
        current = Decimal(offer.normalised_unit_price.amount)
        if current <= 0:
            continue
        ratio = current / baseline
        if ratio >= Decimal("8.0") or ratio <= Decimal("0.125"):
            ratio_quantized = ratio.quantize(Decimal("0.0001"))
            ratio_str = format(ratio_quantized, "f")
            recurrence_key = decimal_anomaly_recurrence_key(offer.id, ratio_str)
            confidence: Literal["high", "medium", "low"] = "high" if sample_count >= 3 else "medium"
            severity: Literal["warning", "critical"] = (
                "critical" if ratio >= Decimal("8.0") else "warning"
            )
            alerts.append(
                Alert(
                    id=alert_fingerprint(
                        tenant_id=member.tenant_id,
                        kind="decimal_or_quantity_anomaly",
                        product_id=compare.product.id,
                        supplier_id=offer.supplier_id,
                        recurrence_key=recurrence_key,
                    ),
                    kind="decimal_or_quantity_anomaly",
                    workspace_product_id=compare.product.id,
                    supplier_id=offer.supplier_id,
                    severity=severity,
                    confidence=confidence,
                    action="review_quotation",
                    evidence={
                        "landed_cost_id": str(offer.id),
                        "quotation_line_id": str(offer.quotation_line_id),
                        "current_price": offer.normalised_unit_price.model_dump(mode="json"),
                        "baseline_price": window_metric.value.model_dump(mode="json"),
                        "ratio": ratio_str,
                        "anomaly_type": (
                            "magnitude_spike" if ratio >= Decimal("8.0") else "magnitude_drop"
                        ),
                        "sample_count": sample_count,
                    },
                    valid_until=offer.valid_to,
                    created_from_current_data_at=now,
                    dismissed=False,
                )
            )
    return alerts


def _delivery_cost_alerts(
    settings: Settings,
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    active_offers = [o for o in compare.offers if not getattr(o, "is_expired", False)]
    supplier_ids = {o.supplier_id for o in active_offers}
    if not supplier_ids:
        return []
    alerts: list[Alert] = []
    for supplier_id in sorted(supplier_ids, key=str):
        term = _latest_supplier_commercial_term(settings, member, supplier_id)
        if term is None:
            continue
        fee_amount = term.get("delivery_fee_amount")
        mov_amount = term.get("minimum_order_value_amount")
        if fee_amount is None or mov_amount is None:
            continue
        fee = Decimal(str(fee_amount))
        mov = Decimal(str(mov_amount))
        if mov <= 0 or fee <= 0:
            continue
        fee_ratio = fee / mov
        if fee_ratio < Decimal("0.40"):
            continue
        fee_str = format(fee.quantize(Decimal("0.01")), "f")
        recurrence_key = delivery_cost_recurrence_key(supplier_id, fee_str)
        severity: Literal["warning", "critical"] = (
            "critical" if fee_ratio >= Decimal("0.70") else "warning"
        )
        alerts.append(
            Alert(
                id=alert_fingerprint(
                    tenant_id=member.tenant_id,
                    kind="delivery_cost_anomaly",
                    product_id=compare.product.id,
                    supplier_id=supplier_id,
                    recurrence_key=recurrence_key,
                ),
                kind="delivery_cost_anomaly",
                workspace_product_id=compare.product.id,
                supplier_id=supplier_id,
                severity=severity,
                confidence="high",
                action="view_delivery_issues",
                evidence={
                    "supplier_id": str(supplier_id),
                    "delivery_fee": fee_str,
                    "minimum_order_value": format(mov.quantize(Decimal("0.01")), "f"),
                    "fee_ratio": format(fee_ratio.quantize(Decimal("0.0001")), "f"),
                    "currency": str(term.get("delivery_fee_currency") or ""),
                },
                created_from_current_data_at=now,
                dismissed=False,
            )
        )
    return alerts


def _supplier_quality_alerts(
    settings: Settings,
    member: CurrentMember,
    compare: object,
    now: datetime,
) -> list[Alert]:
    active_offers = [o for o in compare.offers if not getattr(o, "is_expired", False)]
    supplier_ids = {o.supplier_id for o in active_offers}
    if not supplier_ids:
        return []
    alerts: list[Alert] = []
    for supplier_id in sorted(supplier_ids, key=str):
        quality_data = _get_supplier_quality_stats(settings, member, supplier_id)
        if quality_data is None:
            continue
        dispute_rate, quality_score, incident_count, sample_count = quality_data
        is_anomaly = (
            (sample_count >= 3 and quality_score <= Decimal("0.80"))
            or (sample_count >= 3 and dispute_rate >= Decimal("0.05"))
            or incident_count >= 2
        )
        if not is_anomaly:
            continue
        dispute_str = format(dispute_rate.quantize(Decimal("0.0001")), "f")
        quality_str = format(quality_score.quantize(Decimal("0.0001")), "f")
        recurrence_key = supplier_quality_recurrence_key(
            supplier_id, dispute_str, quality_str, incident_count
        )
        severity: Literal["warning", "critical"] = (
            "critical"
            if (dispute_rate >= Decimal("0.10") or quality_score <= Decimal("0.70"))
            else "warning"
        )
        confidence: Literal["high", "medium", "low"] = (
            "high" if sample_count >= 10 else ("medium" if sample_count >= 3 else "low")
        )
        alerts.append(
            Alert(
                id=alert_fingerprint(
                    tenant_id=member.tenant_id,
                    kind="supplier_quality_trend_change",
                    product_id=compare.product.id,
                    supplier_id=supplier_id,
                    recurrence_key=recurrence_key,
                ),
                kind="supplier_quality_trend_change",
                workspace_product_id=compare.product.id,
                supplier_id=supplier_id,
                severity=severity,
                confidence=confidence,
                action="inspect_scorecard",
                evidence={
                    "supplier_id": str(supplier_id),
                    "dispute_rate": dispute_str,
                    "quality_score": quality_str,
                    "incident_count": incident_count,
                    "sample_count": sample_count,
                },
                created_from_current_data_at=now,
                dismissed=False,
            )
        )
    return alerts


def _latest_supplier_commercial_term(
    settings: Settings,
    member: CurrentMember,
    supplier_id: UUID,
) -> dict[str, object] | None:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select delivery_fee_amount, minimum_order_value_amount, delivery_fee_currency
                from supplier_commercial_term
                where supplier_id = %s
                order by effective_from desc, created_at desc, id desc
                limit 1
                """,
                (supplier_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _get_supplier_quality_stats(
    settings: Settings,
    member: CurrentMember,
    supplier_id: UUID,
) -> tuple[Decimal, Decimal, int, int] | None:
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=180)).date()
    today = now.date()
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select count(*) as sample_count,
                       count(*) filter (where delivery_result = 'disputed') as dispute_count
                from purchase_record
                where supplier_id = %s
                  and recorded_at >= %s
                  and recorded_at <= %s
                """,
                (supplier_id, window_start, today),
            )
            purchases = cur.fetchone()
            sample_count = int(purchases["sample_count"]) if purchases else 0
            dispute_count = int(purchases["dispute_count"]) if purchases else 0

            cur.execute(
                """
                select count(distinct dqi.id) as incident_count
                from delivery_quality_issue dqi
                join purchase_request pr on pr.id = dqi.purchase_request_id
                join purchase_request_line prl on prl.purchase_request_id = pr.id
                join landed_cost lc on lc.id = prl.estimated_unit_price_source_landed_cost_id
                join quotation_line ql on ql.id = lc.quotation_line_id
                join quotation q on q.id = ql.quotation_id
                where q.supplier_id = %s
                  and dqi.created_at >= %s
                  and dqi.created_at <= %s
                """,
                (supplier_id, window_start, today),
            )
            issues = cur.fetchone()
            incident_count = int(issues["incident_count"]) if issues else 0

    if sample_count == 0 and incident_count == 0:
        return None

    dispute_rate = (
        Decimal(dispute_count) / Decimal(sample_count) if sample_count > 0 else Decimal("0")
    )
    issue_rate = (
        Decimal(incident_count) / Decimal(sample_count) if sample_count > 0 else Decimal("1")
    )
    quality_score = max(Decimal("0"), Decimal("1.0000") - issue_rate)
    return (dispute_rate, quality_score, incident_count, sample_count)
