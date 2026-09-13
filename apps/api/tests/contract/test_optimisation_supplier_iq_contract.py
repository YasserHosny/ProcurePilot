from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.main import create_app
from procurepilot_api.modules.offers.schemas import (
    AdvancedBasketAllocationLine,
    AdvancedBasketOptimiseRequest,
    AdvancedBasketResult,
    AdvancedSupplierAllocation,
    AnomalySignal,
    BasketItemRequest,
    Money,
    OptimisationConstraint,
    OptimisationWeights,
    SupplierCommercialTerm,
    SupplierCommercialTermCreate,
    SupplierCommercialTermList,
    SupplierQuantityTier,
    SupplierRiskScore,
    SupplierRiskSubScore,
    SupplierScorecard,
    SupplierScoreMetric,
    ViolatedOptimisationConstraint,
)


def test_advanced_basket_contract_includes_constraints_evidence_and_money() -> None:
    supplier_ids = [uuid4(), uuid4(), uuid4()]
    product_id = uuid4()
    offer_id = uuid4()
    landed_cost_id = uuid4()
    request = AdvancedBasketOptimiseRequest(
        supplier_ids=supplier_ids,
        items=[BasketItemRequest(workspace_product_id=product_id, quantity="12.000000")],
        risk_tolerance="medium",
        urgency="urgent",
        excluded_supplier_ids=[supplier_ids[2]],
        weights=OptimisationWeights(
            price=0.5,
            preferred_supplier=0.2,
            risk=0.15,
            lead_time=0.1,
            quality=0.05,
        ),
    )
    result = AdvancedBasketResult(
        feasible=True,
        allocation=[
            AdvancedSupplierAllocation(
                supplier_id=supplier_ids[0],
                lines=[
                    AdvancedBasketAllocationLine(
                        workspace_product_id=product_id,
                        supplier_id=supplier_ids[0],
                        quantity="12.000000",
                        offer_id=offer_id,
                        landed_cost=Money(amount="120.0000", currency="GBP"),
                        applied_tier_id="tier-12",
                    )
                ],
                total_landed_cost=Money(amount="120.0000", currency="GBP"),
            )
        ],
        total_landed_cost=Money(amount="120.0000", currency="GBP"),
        applied_constraints=[
            OptimisationConstraint(
                kind="quantity_tier",
                supplier_id=supplier_ids[0],
                workspace_product_id=product_id,
                description="Quantity tier applied",
                money=Money(amount="10.0000", currency="GBP"),
                source_ids=[landed_cost_id],
            )
        ],
        violated_constraints=[],
        risk_notes=["Supplier risk below requested tolerance."],
        confidence="medium",
        source_landed_cost_ids=[landed_cost_id],
        solver_version="advanced-basket-v1",
        computed_at=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(days=7),
    )

    dumped = result.model_dump(mode="json")
    assert request.supplier_ids == supplier_ids
    assert dumped["total_landed_cost"] == {"amount": "120.0000", "currency": "GBP"}
    assert dumped["applied_constraints"][0]["source_ids"] == [str(landed_cost_id)]


def test_advanced_basket_request_rejects_duplicate_or_unknown_supplier_sets() -> None:
    supplier_id = uuid4()
    with pytest.raises(ValidationError, match="unique suppliers"):
        AdvancedBasketOptimiseRequest(
            supplier_ids=[supplier_id, supplier_id],
            items=[BasketItemRequest(workspace_product_id=uuid4(), quantity="1.000000")],
            risk_tolerance="low",
            urgency="normal",
            weights=_weights(),
        )

    with pytest.raises(ValidationError, match="selected suppliers"):
        AdvancedBasketOptimiseRequest(
            supplier_ids=[uuid4(), uuid4()],
            items=[BasketItemRequest(workspace_product_id=uuid4(), quantity="1.000000")],
            risk_tolerance="low",
            urgency="normal",
            excluded_supplier_ids=[uuid4()],
            weights=_weights(),
        )


def test_supplier_terms_contract_preserves_money_pairs_and_quantity_tiers() -> None:
    supplier_id = uuid4()
    term = SupplierCommercialTerm(
        id=uuid4(),
        supplier_id=supplier_id,
        effective_from=datetime.now(UTC),
        effective_to=None,
        minimum_order_value=Money(amount="250.0000", currency="GBP"),
        delivery_fee=Money(amount="12.5000", currency="GBP"),
        free_delivery_threshold=Money(amount="500.0000", currency="GBP"),
        quantity_tiers=[
            SupplierQuantityTier(
                workspace_product_id=uuid4(),
                min_quantity="24.000000",
                unit_price=Money(amount="9.7500", currency="GBP"),
            )
        ],
        rule_version="supplier-commercial-terms-v1",
        created_at=datetime.now(UTC),
    )
    listed = SupplierCommercialTermList(items=[term]).model_dump(mode="json")

    assert listed["items"][0]["minimum_order_value"] == {
        "amount": "250.0000",
        "currency": "GBP",
    }
    assert listed["items"][0]["quantity_tiers"][0]["unit_price"]["currency"] == "GBP"


def test_supplier_terms_contract_rejects_invalid_effective_window() -> None:
    effective_from = datetime.now(UTC)
    with pytest.raises(ValidationError, match="effective_to must be after effective_from"):
        SupplierCommercialTermCreate(
            effective_from=effective_from,
            effective_to=effective_from,
        )


def test_supplier_scorecard_contract_carries_metric_evidence_and_risk_breakdown() -> None:
    supplier_id = uuid4()
    today = date.today()
    scorecard = SupplierScorecard(
        supplier_id=supplier_id,
        window_start=today - timedelta(days=180),
        window_end=today,
        metrics={
            "fulfilment_rate": SupplierScoreMetric(
                value="0.9200",
                sample_count=25,
                source_ids=[uuid4()],
                confidence="high",
                insufficient_evidence=False,
                window_start=today - timedelta(days=180),
                window_end=today,
            )
        },
        risk_score=SupplierRiskScore(
            total="0.1800",
            confidence="medium",
            rule_version="supplier-risk-v1",
            sub_scores=[
                SupplierRiskSubScore(
                    name="quality",
                    score="0.2000",
                    weight="0.3000",
                    evidence={"quality_issue_count": 1},
                )
            ],
        ),
        source_counts={"purchase_record": 25, "delivery_quality_issue": 1},
        confidence="medium",
        insufficient_evidence=False,
        computed_at=datetime.now(UTC),
        rule_version="supplier-scorecard-v1",
    )

    dumped = scorecard.model_dump(mode="json")
    assert dumped["supplier_id"] == str(supplier_id)
    assert dumped["metrics"]["fulfilment_rate"]["sample_count"] == 25
    assert dumped["risk_score"]["sub_scores"][0]["evidence"]["quality_issue_count"] == 1


def test_anomaly_alert_contract_supports_all_r2_4_kinds() -> None:
    for kind in (
        "price_spike",
        "likely_duplicate_quotation_line",
        "decimal_or_quantity_anomaly",
        "delivery_cost_anomaly",
        "supplier_quality_trend_change",
    ):
        alert = AnomalySignal(
            id=f"{kind}:fingerprint",
            kind=kind,
            workspace_product_id=uuid4(),
            supplier_id=uuid4(),
            severity="warning",
            confidence="medium",
            evidence={"source_landed_cost_ids": [str(uuid4())]},
            action="inspect_supplier_scorecard",
            valid_until=datetime.now(UTC) + timedelta(days=3),
            created_from_current_data_at=datetime.now(UTC),
            dismissed=False,
        )
        assert alert.model_dump(mode="json")["kind"] == kind


def test_supplier_terms_routes_are_registered_on_api_prefix() -> None:
    app_paths = {route.path for route in create_app().routes}
    assert "/api/v1/suppliers/{supplier_id}/commercial-terms" in app_paths


def test_advanced_basket_result_requires_structured_violations_not_worker_failure() -> None:
    violation = ViolatedOptimisationConstraint(
        kind="minimum_order_value",
        supplier_id=uuid4(),
        description="Minimum order value was not reached",
        money=Money(amount="250.0000", currency="GBP"),
        reason="basket_total_below_minimum_order_value",
    )
    dumped = AdvancedBasketResult(
        feasible=False,
        allocation=[],
        total_landed_cost=None,
        applied_constraints=[],
        violated_constraints=[violation],
        risk_notes=[],
        confidence="low",
        source_landed_cost_ids=[],
        solver_version="advanced-basket-v1",
        computed_at=datetime.now(UTC),
    ).model_dump(mode="json")

    assert dumped["feasible"] is False
    assert dumped["violated_constraints"][0]["reason"] == "basket_total_below_minimum_order_value"


def _weights() -> OptimisationWeights:
    return OptimisationWeights(
        price=0.5,
        preferred_supplier=0.2,
        risk=0.1,
        lead_time=0.1,
        quality=0.1,
    )
