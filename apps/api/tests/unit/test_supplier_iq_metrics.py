from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from procurepilot_api.modules.offers.supplier_iq import (
    SUPPLIER_RISK_RULE_VERSION,
    SUPPLIER_SCORECARD_RULE_VERSION,
    SupplierIqSourceData,
    calculate_scorecard,
)


def test_supplier_iq_metrics_are_deterministic_and_evidence_backed() -> None:
    supplier_id = uuid4()
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    scorecard = calculate_scorecard(
        supplier_id=supplier_id,
        window_start=date(2026, 3, 17),
        window_end=date(2026, 9, 13),
        computed_at=now,
        source_data=_source_data(now),
    )

    assert scorecard.metrics["fulfilment_rate"].value == "0.5000"
    assert scorecard.metrics["fulfilment_rate"].sample_count == 3
    assert scorecard.metrics["quality_score"].value == "0.6667"
    assert scorecard.metrics["price_competitiveness"].value == "0.7667"
    assert scorecard.metrics["spend_exposure"].value == "0.6000"
    assert scorecard.metrics["freshness_score"].value == "0.9444"
    assert scorecard.metrics["savings_contribution"].value == "0.3000"
    assert all(metric.source_ids for metric in scorecard.metrics.values())
    assert not scorecard.insufficient_evidence
    assert scorecard.source_counts == {
        "purchase_record": 3,
        "tenant_purchase_record": 5,
        "delivery_quality_issue": 1,
        "landed_cost": 3,
        "market_landed_cost": 3,
        "saving_record": 2,
        "tenant_saving_record": 4,
    }


def test_supplier_iq_sparse_evidence_is_explicit() -> None:
    supplier_id = uuid4()
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    scorecard = calculate_scorecard(
        supplier_id=supplier_id,
        window_start=date(2026, 3, 17),
        window_end=date(2026, 9, 13),
        computed_at=now,
        source_data=SupplierIqSourceData(
            purchase_records=[_purchase("delivered", "12.0000", now - timedelta(days=3))],
            tenant_purchase_records=[
                _purchase("delivered", "12.0000", now - timedelta(days=3))
            ],
            quality_issues=[],
            landed_costs=[],
            market_landed_costs=[],
            saving_records=[],
            tenant_saving_records=[],
        ),
    )

    assert scorecard.insufficient_evidence
    assert scorecard.confidence == "low"
    assert scorecard.metrics["fulfilment_rate"].value is None
    assert scorecard.metrics["fulfilment_rate"].insufficient_evidence
    assert scorecard.metrics["quality_score"].value is None
    assert scorecard.metrics["savings_contribution"].insufficient_evidence


def test_supplier_iq_risk_score_is_rule_versioned_and_replayable() -> None:
    supplier_id = uuid4()
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    first = calculate_scorecard(
        supplier_id=supplier_id,
        window_start=date(2026, 3, 17),
        window_end=date(2026, 9, 13),
        computed_at=now,
        source_data=_source_data(now),
    )
    second = calculate_scorecard(
        supplier_id=supplier_id,
        window_start=date(2026, 3, 17),
        window_end=date(2026, 9, 13),
        computed_at=now,
        source_data=_source_data(now),
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.rule_version == SUPPLIER_SCORECARD_RULE_VERSION
    assert first.risk_score.rule_version == SUPPLIER_RISK_RULE_VERSION
    assert first.risk_score.total == "0.3605"
    assert {sub_score.name for sub_score in first.risk_score.sub_scores} == {
        "fulfilment",
        "quality",
        "price",
        "exposure",
        "freshness",
        "savings",
    }


def _source_data(now: datetime) -> SupplierIqSourceData:
    product_ids = [UUID(int=index) for index in range(1, 4)]
    return SupplierIqSourceData(
        purchase_records=[
            _purchase("delivered", "10.0000", now - timedelta(days=20)),
            _purchase("partially_delivered", "20.0000", now - timedelta(days=15)),
            _purchase("disputed", "30.0000", now - timedelta(days=10)),
        ],
        tenant_purchase_records=[
            _purchase("delivered", "10.0000", now - timedelta(days=20)),
            _purchase("partially_delivered", "20.0000", now - timedelta(days=15)),
            _purchase("disputed", "30.0000", now - timedelta(days=10)),
            _purchase("delivered", "15.0000", now - timedelta(days=8)),
            _purchase("delivered", "25.0000", now - timedelta(days=7)),
        ],
        quality_issues=[_row(created_at=now - timedelta(days=9))],
        landed_costs=[
            _price(product_ids[0], "10.0000", now - timedelta(days=40)),
            _price(product_ids[1], "10.0000", now - timedelta(days=39)),
            _price(product_ids[2], "10.0000", now - timedelta(days=38)),
        ],
        market_landed_costs=[
            _price(product_ids[0], "8.0000", now - timedelta(days=37)),
            _price(product_ids[1], "10.0000", now - timedelta(days=36)),
            _price(product_ids[2], "5.0000", now - timedelta(days=35)),
        ],
        saving_records=[
            _saving("10.0000", now - timedelta(days=12)),
            _saving("20.0000", now - timedelta(days=11)),
        ],
        tenant_saving_records=[
            _saving("10.0000", now - timedelta(days=12)),
            _saving("20.0000", now - timedelta(days=11)),
            _saving("30.0000", now - timedelta(days=10)),
            _saving("40.0000", now - timedelta(days=9)),
        ],
    )


def _purchase(result: str, total: str, recorded_at: datetime) -> dict[str, object]:
    return _row(
        delivery_result=result,
        total_paid_amount=Decimal(total),
        total_paid_currency="GBP",
        recorded_at=recorded_at,
    )


def _price(product_id: UUID, unit_price: str, recorded_at: datetime) -> dict[str, object]:
    return _row(
        workspace_product_id=product_id,
        normalised_unit_price=Decimal(unit_price),
        currency="GBP",
        recorded_at=recorded_at,
    )


def _saving(delta: str, recorded_at: datetime) -> dict[str, object]:
    return _row(delta_amount=Decimal(delta), delta_currency="GBP", recorded_at=recorded_at)


def _row(**values: object) -> dict[str, object]:
    fingerprint = repr(sorted((key, str(value)) for key, value in values.items()))
    return {"id": uuid5(NAMESPACE_URL, fingerprint), **values}
