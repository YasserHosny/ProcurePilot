from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.alerts.fingerprints import alert_fingerprint
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
