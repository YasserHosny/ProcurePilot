from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from procurepilot_optimiser_worker.models import (
    AdvancedBasketRequest,
    AdvancedBasketResult,
    AdvancedOfferInput,
    AdvancedOptimisationInput,
    AppliedConstraint,
    BasketItem,
    Money,
    OptimisationConfidence,
    OptimisationHardConstraints,
    QuantityTier,
    RiskNote,
    SupplierCommercialTerms,
    SupplierRiskSignal,
)

RULE_VERSION = "advanced-basket-optimiser-v1"


def _money(amount: str, currency: str = "GBP") -> Money:
    return Money(amount=amount, currency=currency)


def _item(product_id: UUID, quantity: str = "1.000000") -> BasketItem:
    return BasketItem(workspace_product_id=product_id, quantity=quantity)


def _request(
    *,
    supplier_ids: list[UUID],
    items: list[BasketItem],
    hard_constraints: OptimisationHardConstraints | None = None,
) -> AdvancedBasketRequest:
    return AdvancedBasketRequest(
        id=uuid4(),
        tenant_id=uuid4(),
        supplier_ids=supplier_ids,
        items=items,
        hard_constraints=hard_constraints or OptimisationHardConstraints(),
        rule_version=RULE_VERSION,
    )


def _offer(
    *,
    product_id: UUID,
    supplier_id: UUID,
    total: str,
    unit: str | None = None,
) -> AdvancedOfferInput:
    return AdvancedOfferInput(
        offer_id=uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        quantity="1.000000",
        total_landed_cost=_money(total),
        unit_landed_cost=_money(unit or total),
        source_landed_cost_id=uuid4(),
    )


def _risk(supplier_id: UUID, score: str) -> SupplierRiskSignal:
    return SupplierRiskSignal(
        supplier_id=supplier_id,
        risk_score=score,
        confidence="0.9000",
        insufficient_evidence=False,
        source_ids=[uuid4()],
        rule_version="supplier-risk-v1",
    )


def _advanced_solver(input_payload: AdvancedOptimisationInput) -> object:
    from procurepilot_optimiser_worker import solver

    return solver.solve_advanced_basket(input_payload=input_payload)


def test_advanced_request_accepts_two_to_ten_unique_suppliers_and_fifty_lines() -> None:
    suppliers = [uuid4() for _ in range(10)]
    items = [_item(uuid4()) for _ in range(50)]

    request = _request(supplier_ids=suppliers, items=items)

    assert request.supplier_ids == suppliers
    assert len(request.items) == 50
    assert request.rule_version == RULE_VERSION


@pytest.mark.parametrize("supplier_count", [1, 11])
def test_advanced_request_rejects_supplier_counts_outside_r2_4_bounds(
    supplier_count: int,
) -> None:
    with pytest.raises(ValidationError):
        _request(
            supplier_ids=[uuid4() for _ in range(supplier_count)],
            items=[_item(uuid4())],
        )


def test_advanced_request_rejects_duplicate_or_fully_excluded_suppliers() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    item = _item(uuid4())

    with pytest.raises(ValidationError, match="unique suppliers"):
        _request(supplier_ids=[supplier_a, supplier_a], items=[item])

    with pytest.raises(ValidationError, match="leave no eligible suppliers"):
        _request(
            supplier_ids=[supplier_a, supplier_b],
            items=[item],
            hard_constraints=OptimisationHardConstraints(
                excluded_supplier_ids=[supplier_a, supplier_b]
            ),
        )


def test_advanced_input_refuses_mixed_offer_and_term_currencies() -> None:
    supplier_a = uuid4()
    supplier_b = uuid4()
    product_id = uuid4()
    request = _request(
        supplier_ids=[supplier_a, supplier_b],
        items=[_item(product_id)],
    )

    with pytest.raises(ValidationError, match="mixed currencies"):
        AdvancedOptimisationInput(
            request=request,
            offers=[
                _offer(product_id=product_id, supplier_id=supplier_a, total="10.0000"),
                AdvancedOfferInput(
                    offer_id=uuid4(),
                    workspace_product_id=product_id,
                    supplier_id=supplier_b,
                    quantity="1.000000",
                    total_landed_cost=_money("9.0000", "EUR"),
                    unit_landed_cost=_money("9.0000", "EUR"),
                    source_landed_cost_id=uuid4(),
                ),
            ],
        )

    with pytest.raises(ValidationError, match="mixed currencies"):
        AdvancedOptimisationInput(
            request=request,
            offers=[_offer(product_id=product_id, supplier_id=supplier_a, total="10.0000")],
            supplier_terms=[
                SupplierCommercialTerms(
                    supplier_id=supplier_a,
                    rule_version="supplier-commercial-terms-v1",
                    minimum_order_value=_money("50.0000", "EUR"),
                )
            ],
        )


def test_advanced_models_carry_terms_risk_confidence_and_evidence() -> None:
    supplier_id = uuid4()
    product_id = uuid4()
    source_term_id = uuid4()
    valid_until = datetime.now(UTC) + timedelta(days=7)

    terms = SupplierCommercialTerms(
        supplier_id=supplier_id,
        rule_version="supplier-commercial-terms-v1",
        minimum_order_value=_money("75.0000"),
        delivery_fee=_money("8.0000"),
        free_delivery_threshold=_money("100.0000"),
        quantity_tiers=[
            QuantityTier(
                workspace_product_id=product_id,
                min_quantity="10.000000",
                unit_price=_money("4.5000"),
                source_term_id=source_term_id,
            )
        ],
    )
    risk = RiskNote(
        supplier_id=supplier_id,
        severity="medium",
        message="late deliveries exceeded tolerance",
        confidence="0.7400",
        source_ids=[uuid4()],
    )
    applied = AppliedConstraint(
        kind="quantity_tier",
        supplier_id=supplier_id,
        workspace_product_id=product_id,
        description="tier applied at 10 units",
        source_ids=[source_term_id],
    )
    confidence = OptimisationConfidence(
        score="0.8100",
        insufficient_evidence=False,
        reasons=["current offers and supplier terms available"],
    )
    result = AdvancedBasketResult(
        feasible=False,
        allocation=[],
        total_landed_cost=None,
        single_supplier_baselines=[],
        applied_constraints=[applied],
        violated_constraints=[],
        risk_notes=[risk],
        confidence=confidence,
        valid_until=valid_until,
        source_landed_cost_ids=[uuid4()],
        solver_version="advanced-basket-cp-sat-v1",
        rule_version=RULE_VERSION,
        computed_at=datetime.now(UTC),
    )

    assert terms.quantity_tiers[0].min_quantity_decimal == 10
    assert risk.confidence == "0.7400"
    assert applied.source_ids == [source_term_id]
    assert result.confidence.score == "0.8100"
    assert result.advisory_only is True
    with pytest.raises(ValidationError):
        AdvancedBasketResult(
            feasible=False,
            allocation=[],
            total_landed_cost=None,
            single_supplier_baselines=[],
            applied_constraints=[],
            violated_constraints=[],
            risk_notes=[],
            confidence=confidence,
            valid_until=valid_until,
            source_landed_cost_ids=[],
            solver_version="advanced-basket-cp-sat-v1",
            rule_version=RULE_VERSION,
            computed_at=datetime.now(UTC),
            advisory_only=False,
        )


@pytest.mark.xfail(reason="T018 will implement advanced MOV constraints", strict=False)
def test_solver_enforces_minimum_order_value_before_using_supplier() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id)],
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="40.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="45.0000"),
        ],
        supplier_terms=[
            SupplierCommercialTerms(
                supplier_id=supplier_a,
                rule_version="supplier-commercial-terms-v1",
                minimum_order_value=_money("50.0000"),
            )
        ],
    )

    result = _advanced_solver(payload)

    assert result.feasible is True
    assert result.allocation[0].supplier_id == supplier_b
    assert any(
        violation.kind == "minimum_order_value" and violation.supplier_id == supplier_a
        for violation in result.violated_constraints
    )


@pytest.mark.xfail(reason="T018 will implement delivery fee threshold economics", strict=False)
def test_solver_applies_delivery_fee_until_free_delivery_threshold() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id)],
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="95.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="100.0000"),
        ],
        supplier_terms=[
            SupplierCommercialTerms(
                supplier_id=supplier_a,
                rule_version="supplier-commercial-terms-v1",
                delivery_fee=_money("10.0000"),
                free_delivery_threshold=_money("100.0000"),
            )
        ],
    )

    result = _advanced_solver(payload)

    assert result.total_landed_cost == _money("100.0000")
    assert any(constraint.kind == "delivery_fee" for constraint in result.applied_constraints)


@pytest.mark.xfail(reason="T018 will implement quantity tier pricing", strict=False)
def test_solver_uses_quantity_tiers_when_requested_quantity_crosses_break() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    source_term_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id, "10.000000")],
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="60.0000", unit="6.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="55.0000", unit="5.5000"),
        ],
        supplier_terms=[
            SupplierCommercialTerms(
                supplier_id=supplier_a,
                rule_version="supplier-commercial-terms-v1",
                quantity_tiers=[
                    QuantityTier(
                        workspace_product_id=product_id,
                        min_quantity="10.000000",
                        unit_price=_money("5.0000"),
                        source_term_id=source_term_id,
                    )
                ],
            )
        ],
    )

    result = _advanced_solver(payload)

    assert result.total_landed_cost == _money("50.0000")
    assert any(source_term_id in constraint.source_ids for constraint in result.applied_constraints)


@pytest.mark.xfail(reason="T018 will implement risk tolerance filtering", strict=False)
def test_solver_respects_risk_tolerance_even_when_cheapest_supplier_is_risky() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id)],
            hard_constraints=OptimisationHardConstraints(max_supplier_risk="0.5000"),
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="8.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="10.0000"),
        ],
        supplier_risks=[_risk(supplier_a, "0.9000"), _risk(supplier_b, "0.2000")],
    )

    result = _advanced_solver(payload)

    assert result.feasible is True
    assert result.allocation[0].supplier_id == supplier_b
    assert any(note.supplier_id == supplier_a for note in result.risk_notes)


@pytest.mark.xfail(reason="T018 will implement supplier exclusion filtering", strict=False)
def test_solver_respects_explicit_supplier_exclusion() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id)],
            hard_constraints=OptimisationHardConstraints(excluded_supplier_ids=[supplier_a]),
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="1.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="9.0000"),
        ],
    )

    result = _advanced_solver(payload)

    assert result.feasible is True
    assert result.allocation[0].supplier_id == supplier_b
    assert any(
        constraint.kind == "supplier_exclusion" and constraint.supplier_id == supplier_a
        for constraint in result.applied_constraints
    )


@pytest.mark.xfail(reason="T018 will return infeasible advanced constraint results", strict=False)
def test_solver_reports_infeasible_constraints_as_completed_result() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_a, supplier_b],
            items=[_item(product_id)],
            hard_constraints=OptimisationHardConstraints(max_supplier_risk="0.1000"),
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="8.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="10.0000"),
        ],
        supplier_risks=[_risk(supplier_a, "0.9000"), _risk(supplier_b, "0.8000")],
    )

    result = _advanced_solver(payload)

    assert result.feasible is False
    assert result.total_landed_cost is None
    assert {violation.kind for violation in result.violated_constraints} == {"risk_tolerance"}


@pytest.mark.xfail(reason="T018 will disclose deterministic tie-break order", strict=False)
def test_solver_uses_deterministic_tie_break_for_equal_cost_allocations() -> None:
    supplier_a = UUID("00000000-0000-0000-0000-00000000000a")
    supplier_b = UUID("00000000-0000-0000-0000-00000000000b")
    product_id = uuid4()
    payload = AdvancedOptimisationInput(
        request=_request(
            supplier_ids=[supplier_b, supplier_a],
            items=[_item(product_id)],
        ),
        offers=[
            _offer(product_id=product_id, supplier_id=supplier_a, total="10.0000"),
            _offer(product_id=product_id, supplier_id=supplier_b, total="10.0000"),
        ],
    )

    first = _advanced_solver(payload)
    second = _advanced_solver(payload)

    assert first == second
    assert first.allocation[0].supplier_id == supplier_a
    assert any("supplier_id" in constraint.description for constraint in first.applied_constraints)
