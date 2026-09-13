from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.offers.schemas import (
    SupplierRiskScore,
    SupplierRiskSubScore,
    SupplierScorecard,
    SupplierScoreMetric,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.modules.offers.supplier_terms import _supplier_visible
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

SUPPLIER_SCORECARD_RULE_VERSION = "supplier-scorecard-v1"
SUPPLIER_RISK_RULE_VERSION = "supplier-risk-v1"
DEFAULT_WINDOW_DAYS = 180
MIN_SAMPLE_COUNT = 3
FRESHNESS_TARGET_DAYS = Decimal("180")


@dataclass(frozen=True)
class SupplierIqSourceData:
    purchase_records: list[dict[str, object]]
    tenant_purchase_records: list[dict[str, object]]
    quality_issues: list[dict[str, object]]
    landed_costs: list[dict[str, object]]
    market_landed_costs: list[dict[str, object]]
    saving_records: list[dict[str, object]]
    tenant_saving_records: list[dict[str, object]]


class SupplierIqService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def get_scorecard(
        self,
        *,
        member: CurrentMember,
        supplier_id: UUID,
        bearer_token: str | None = None,
    ) -> SupplierScorecard:
        today = datetime.now(UTC).date()
        window_start = today - timedelta(days=DEFAULT_WINDOW_DAYS)
        with _authenticated_db(self._settings, member) as conn:
            _supplier_visible(conn, supplier_id)
            source_data = _load_source_data(
                conn,
                supplier_id=supplier_id,
                window_start=window_start,
                window_end=today,
            )
            scorecard = calculate_scorecard(
                supplier_id=supplier_id,
                window_start=window_start,
                window_end=today,
                computed_at=datetime.now(UTC),
                source_data=source_data,
            )
            _persist_snapshot(conn, member=member, scorecard=scorecard)
        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="supplier_iq.scorecard_viewed",
            target={
                "supplier_id": str(supplier_id),
                "window_start": scorecard.window_start.isoformat(),
                "window_end": scorecard.window_end.isoformat(),
                "rule_version": scorecard.rule_version,
            },
        )
        return scorecard


def get_supplier_iq_service() -> SupplierIqService:
    return SupplierIqService()


def calculate_scorecard(
    *,
    supplier_id: UUID,
    window_start: date,
    window_end: date,
    computed_at: datetime,
    source_data: SupplierIqSourceData,
) -> SupplierScorecard:
    metrics = {
        "fulfilment_rate": _fulfilment_metric(source_data, window_start, window_end),
        "quality_score": _quality_metric(source_data, window_start, window_end),
        "price_competitiveness": _price_metric(source_data, window_start, window_end),
        "spend_exposure": _spend_exposure_metric(source_data, window_start, window_end),
        "freshness_score": _freshness_metric(source_data, window_start, window_end, computed_at),
        "savings_contribution": _savings_metric(source_data, window_start, window_end),
    }
    risk_score = _risk_score(metrics)
    source_counts = {
        "purchase_record": len(source_data.purchase_records),
        "tenant_purchase_record": len(source_data.tenant_purchase_records),
        "delivery_quality_issue": len(source_data.quality_issues),
        "landed_cost": len(source_data.landed_costs),
        "market_landed_cost": len(source_data.market_landed_costs),
        "saving_record": len(source_data.saving_records),
        "tenant_saving_record": len(source_data.tenant_saving_records),
    }
    insufficient_evidence = any(metric.insufficient_evidence for metric in metrics.values())
    return SupplierScorecard(
        supplier_id=supplier_id,
        window_start=window_start,
        window_end=window_end,
        metrics=metrics,
        risk_score=risk_score,
        source_counts=source_counts,
        confidence=_combined_confidence(metric.confidence for metric in metrics.values()),
        insufficient_evidence=insufficient_evidence,
        computed_at=computed_at,
        rule_version=SUPPLIER_SCORECARD_RULE_VERSION,
    )


def _fulfilment_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
) -> SupplierScoreMetric:
    rows = source_data.purchase_records
    sample_count = len(rows)
    value: Decimal | None = None
    if sample_count >= MIN_SAMPLE_COUNT:
        score = sum(_delivery_score(str(row["delivery_result"])) for row in rows)
        value = score / Decimal(sample_count)
    return _metric(
        value=value,
        sample_count=sample_count,
        source_ids=_ids(rows),
        window_start=window_start,
        window_end=window_end,
    )


def _quality_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
) -> SupplierScoreMetric:
    sample_count = len(source_data.purchase_records)
    value: Decimal | None = None
    if sample_count >= MIN_SAMPLE_COUNT:
        issue_rate = Decimal(len(source_data.quality_issues)) / Decimal(sample_count)
        value = max(Decimal("0"), Decimal("1") - issue_rate)
    return _metric(
        value=value,
        sample_count=sample_count,
        source_ids=[*_ids(source_data.purchase_records), *_ids(source_data.quality_issues)],
        window_start=window_start,
        window_end=window_end,
    )


def _price_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
) -> SupplierScoreMetric:
    sample_count = len(source_data.landed_costs)
    ratios: list[Decimal] = []
    market_by_product: dict[UUID, list[dict[str, object]]] = {}
    for row in source_data.market_landed_costs:
        market_by_product.setdefault(UUID(str(row["workspace_product_id"])), []).append(row)
    for row in source_data.landed_costs:
        product_id = UUID(str(row["workspace_product_id"]))
        supplier_price = Decimal(str(row["normalised_unit_price"]))
        competitors = [
            Decimal(str(market_row["normalised_unit_price"]))
            for market_row in market_by_product.get(product_id, [])
            if str(market_row["currency"]) == str(row["currency"])
        ]
        if supplier_price > 0 and competitors:
            ratios.append(min(Decimal("1"), min(competitors) / supplier_price))
    value = (
        sum(ratios, Decimal("0")) / Decimal(len(ratios))
        if len(ratios) >= MIN_SAMPLE_COUNT
        else None
    )
    return _metric(
        value=value,
        sample_count=sample_count,
        source_ids=[*_ids(source_data.landed_costs), *_ids(source_data.market_landed_costs)],
        window_start=window_start,
        window_end=window_end,
    )


def _spend_exposure_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
) -> SupplierScoreMetric:
    supplier_spend = _money_sum(source_data.purchase_records, "total_paid_amount")
    tenant_spend = _money_sum(source_data.tenant_purchase_records, "total_paid_amount")
    value = supplier_spend / tenant_spend if tenant_spend > 0 else None
    return _metric(
        value=value,
        sample_count=len(source_data.purchase_records),
        source_ids=_ids(source_data.purchase_records),
        window_start=window_start,
        window_end=window_end,
        insufficient=value is None,
    )


def _freshness_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
    computed_at: datetime,
) -> SupplierScoreMetric:
    dated_rows = [
        *source_data.purchase_records,
        *source_data.landed_costs,
        *source_data.saving_records,
    ]
    timestamps = [_row_timestamp(row) for row in dated_rows if _row_timestamp(row) is not None]
    value: Decimal | None = None
    if timestamps:
        latest = max(timestamps)
        age_days = max(0, (computed_at - latest).days)
        value = max(Decimal("0"), Decimal("1") - (Decimal(age_days) / FRESHNESS_TARGET_DAYS))
    return _metric(
        value=value,
        sample_count=len(dated_rows),
        source_ids=_ids(dated_rows),
        window_start=window_start,
        window_end=window_end,
        insufficient=value is None,
    )


def _savings_metric(
    source_data: SupplierIqSourceData,
    window_start: date,
    window_end: date,
) -> SupplierScoreMetric:
    supplier_savings = _positive_money_sum(source_data.saving_records, "delta_amount")
    tenant_savings = _positive_money_sum(source_data.tenant_saving_records, "delta_amount")
    value = supplier_savings / tenant_savings if tenant_savings > 0 else None
    return _metric(
        value=value,
        sample_count=len(source_data.saving_records),
        source_ids=_ids(source_data.saving_records),
        window_start=window_start,
        window_end=window_end,
        insufficient=value is None,
    )


def _risk_score(metrics: dict[str, SupplierScoreMetric]) -> SupplierRiskScore:
    components = [
        ("fulfilment", _risk_from_score(metrics["fulfilment_rate"].value), Decimal("0.2500")),
        ("quality", _risk_from_score(metrics["quality_score"].value), Decimal("0.2500")),
        ("price", _risk_from_score(metrics["price_competitiveness"].value), Decimal("0.2000")),
        ("exposure", _decimal_or_half(metrics["spend_exposure"].value), Decimal("0.1500")),
        ("freshness", _risk_from_score(metrics["freshness_score"].value), Decimal("0.1000")),
        (
            "savings",
            max(
                Decimal("0"),
                Decimal("0.5000") - _decimal_or_half(metrics["savings_contribution"].value),
            ),
            Decimal("0.0500"),
        ),
    ]
    sub_scores = [
        SupplierRiskSubScore(
            name=name,
            score=_decimal_string(score),
            weight=_decimal_string(weight),
            evidence={
                "metric": _metric_name_for_risk(name),
                "insufficient_evidence": metrics[_metric_name_for_risk(name)].insufficient_evidence,
                "sample_count": metrics[_metric_name_for_risk(name)].sample_count,
            },
        )
        for name, score, weight in components
    ]
    total = sum(score * weight for _, score, weight in components)
    return SupplierRiskScore(
        total=_decimal_string(min(Decimal("1"), max(Decimal("0"), total))),
        confidence=_combined_confidence(metric.confidence for metric in metrics.values()),
        sub_scores=sub_scores,
        rule_version=SUPPLIER_RISK_RULE_VERSION,
    )


def _metric(
    *,
    value: Decimal | None,
    sample_count: int,
    source_ids: list[UUID],
    window_start: date,
    window_end: date,
    insufficient: bool | None = None,
) -> SupplierScoreMetric:
    insufficient_evidence = (
        sample_count < MIN_SAMPLE_COUNT if insufficient is None else insufficient
    )
    return SupplierScoreMetric(
        value=None if value is None else _decimal_string(value),
        sample_count=sample_count,
        source_ids=_unique_ids(source_ids),
        confidence=_confidence(sample_count),
        insufficient_evidence=insufficient_evidence,
        window_start=window_start,
        window_end=window_end,
    )


def _load_source_data(
    conn: psycopg.Connection,
    *,
    supplier_id: UUID,
    window_start: date,
    window_end: date,
) -> SupplierIqSourceData:
    params = {
        "supplier_id": supplier_id,
        "window_start": window_start,
        "window_end": window_end + timedelta(days=1),
    }
    return SupplierIqSourceData(
        purchase_records=_fetch_rows(conn, _SUPPLIER_PURCHASE_SQL, params),
        tenant_purchase_records=_fetch_rows(conn, _TENANT_PURCHASE_SQL, params),
        quality_issues=_fetch_rows(conn, _QUALITY_SQL, params),
        landed_costs=_fetch_rows(conn, _SUPPLIER_PRICE_SQL, params),
        market_landed_costs=_fetch_rows(conn, _MARKET_PRICE_SQL, params),
        saving_records=_fetch_rows(conn, _SUPPLIER_SAVING_SQL, params),
        tenant_saving_records=_fetch_rows(conn, _TENANT_SAVING_SQL, params),
    )


def _fetch_rows(
    conn: psycopg.Connection,
    query: str,
    params: dict[str, object],
) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def _persist_snapshot(
    conn: psycopg.Connection,
    *,
    member: CurrentMember,
    scorecard: SupplierScorecard,
) -> None:
    with conn.cursor() as cur:
        cur.execute("savepoint supplier_iq_snapshot")
        try:
            cur.execute(
                """
                insert into supplier_scorecard_snapshot (
                  tenant_id,
                  supplier_id,
                  window_start,
                  window_end,
                  rule_version,
                  metrics,
                  risk_score,
                  source_counts,
                  computed_at,
                  computed_by_membership_id
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (tenant_id, supplier_id, window_start, window_end, rule_version)
                do nothing
                """,
                (
                    member.tenant_id,
                    scorecard.supplier_id,
                    scorecard.window_start,
                    scorecard.window_end,
                    scorecard.rule_version,
                    Jsonb(
                        {
                            name: metric.model_dump(mode="json")
                            for name, metric in scorecard.metrics.items()
                        }
                    ),
                    Jsonb(scorecard.risk_score.model_dump(mode="json")),
                    Jsonb(scorecard.source_counts),
                    scorecard.computed_at,
                    member.membership_id,
                ),
            )
        except psycopg.Error:
            cur.execute("rollback to savepoint supplier_iq_snapshot")
        finally:
            cur.execute("release savepoint supplier_iq_snapshot")


def _record_audit(
    *,
    bearer_token: str | None,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=member.tenant_id,
            actor_membership_id=member.membership_id,
            actor_email=member.email,
            action=action,
            target=target,
            outcome="success",
            trace_id=get_trace_id(),
        ),
        bearer_token=bearer_token,
    )


def _delivery_score(result: str) -> Decimal:
    return {
        "delivered": Decimal("1"),
        "partially_delivered": Decimal("0.5000"),
        "ordered": Decimal("0"),
        "cancelled": Decimal("0"),
        "disputed": Decimal("0"),
    }.get(result, Decimal("0"))


def _ids(rows: Iterable[dict[str, object]]) -> list[UUID]:
    return [UUID(str(row["id"])) for row in rows]


def _unique_ids(ids: Iterable[UUID]) -> list[UUID]:
    return [UUID(value) for value in sorted({str(item) for item in ids})]


def _money_sum(rows: Iterable[dict[str, object]], field: str) -> Decimal:
    return sum(
        (Decimal(str(row[field])) for row in rows if row.get(field) is not None),
        Decimal("0"),
    )


def _positive_money_sum(rows: Iterable[dict[str, object]], field: str) -> Decimal:
    return sum(
        (
            max(Decimal("0"), Decimal(str(row[field])))
            for row in rows
            if row.get(field) is not None
        ),
        Decimal("0"),
    )


def _row_timestamp(row: dict[str, object]) -> datetime | None:
    for key in ("recorded_at", "created_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None


def _risk_from_score(value: str | None) -> Decimal:
    return Decimal("1") - _decimal_or_half(value)


def _decimal_or_half(value: str | None) -> Decimal:
    return Decimal("0.5000") if value is None else Decimal(value)


def _metric_name_for_risk(name: str) -> str:
    return {
        "fulfilment": "fulfilment_rate",
        "quality": "quality_score",
        "price": "price_competitiveness",
        "exposure": "spend_exposure",
        "freshness": "freshness_score",
        "savings": "savings_contribution",
    }[name]


def _confidence(sample_count: int) -> str:
    if sample_count >= 10:
        return "high"
    if sample_count >= MIN_SAMPLE_COUNT:
        return "medium"
    return "low"


def _combined_confidence(confidences: Iterable[str]) -> str:
    values = list(confidences)
    if not values or "low" in values:
        return "low"
    if "medium" in values:
        return "medium"
    return "high"


def _decimal_string(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(quantized, "f")


_SUPPLIER_PURCHASE_SQL = """
select id, delivery_result, total_paid_amount, total_paid_currency, recorded_at
from purchase_record
where supplier_id = %(supplier_id)s
  and recorded_at >= %(window_start)s
  and recorded_at < %(window_end)s
order by recorded_at, id
"""

_TENANT_PURCHASE_SQL = """
select id, supplier_id, total_paid_amount, total_paid_currency, recorded_at
from purchase_record
where recorded_at >= %(window_start)s
  and recorded_at < %(window_end)s
order by recorded_at, id
"""

_QUALITY_SQL = """
select distinct dqi.id, dqi.created_at
from delivery_quality_issue dqi
join purchase_request pr
  on pr.tenant_id = dqi.tenant_id
 and pr.id = dqi.purchase_request_id
join purchase_request_line prl
  on prl.tenant_id = pr.tenant_id
 and prl.purchase_request_id = pr.id
join landed_cost lc
  on lc.tenant_id = prl.tenant_id
 and lc.id = prl.estimated_unit_price_source_landed_cost_id
join quotation_line ql
  on ql.tenant_id = lc.tenant_id
 and ql.id = lc.quotation_line_id
join quotation q
  on q.tenant_id = ql.tenant_id
 and q.id = ql.quotation_id
where q.supplier_id = %(supplier_id)s
  and dqi.created_at >= %(window_start)s
  and dqi.created_at < %(window_end)s
order by dqi.created_at, dqi.id
"""

_SUPPLIER_PRICE_SQL = """
select
  lc.id,
  md.matched_workspace_product_id as workspace_product_id,
  (lc.total_amount / nullif(lc.normalised_base_quantity, 0)) as normalised_unit_price,
  lc.total_currency as currency,
  lc.recorded_at
from landed_cost lc
join match_decision md
  on md.tenant_id = lc.tenant_id
 and md.id = lc.match_decision_id
join quotation_line ql
  on ql.tenant_id = lc.tenant_id
 and ql.id = lc.quotation_line_id
join quotation q
  on q.tenant_id = ql.tenant_id
 and q.id = ql.quotation_id
where q.supplier_id = %(supplier_id)s
  and q.status = 'reviewed'
  and lc.recorded_at >= %(window_start)s
  and lc.recorded_at < %(window_end)s
order by lc.recorded_at, lc.id
"""

_MARKET_PRICE_SQL = """
select
  lc.id,
  md.matched_workspace_product_id as workspace_product_id,
  (lc.total_amount / nullif(lc.normalised_base_quantity, 0)) as normalised_unit_price,
  lc.total_currency as currency,
  lc.recorded_at
from landed_cost lc
join match_decision md
  on md.tenant_id = lc.tenant_id
 and md.id = lc.match_decision_id
join quotation_line ql
  on ql.tenant_id = lc.tenant_id
 and ql.id = lc.quotation_line_id
join quotation q
  on q.tenant_id = ql.tenant_id
 and q.id = ql.quotation_id
where q.status = 'reviewed'
  and q.supplier_id is distinct from %(supplier_id)s
  and lc.recorded_at >= %(window_start)s
  and lc.recorded_at < %(window_end)s
order by lc.recorded_at, lc.id
"""

_SUPPLIER_SAVING_SQL = """
select id, delta_amount, delta_currency, recorded_at
from saving_record
where supplier_id = %(supplier_id)s
  and recorded_at >= %(window_start)s
  and recorded_at < %(window_end)s
order by recorded_at, id
"""

_TENANT_SAVING_SQL = """
select id, supplier_id, delta_amount, delta_currency, recorded_at
from saving_record
where recorded_at >= %(window_start)s
  and recorded_at < %(window_end)s
order by recorded_at, id
"""
