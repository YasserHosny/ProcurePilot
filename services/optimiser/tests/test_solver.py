from __future__ import annotations

from uuid import UUID, uuid4

from procurepilot_optimiser_worker.models import (
    AdvancedBasketRequest,
    AdvancedOfferInput,
    AdvancedOptimisationInput,
    BasketItem,
    Money,
    OfferInput,
    OptimisationHardConstraints,
)
from procurepilot_optimiser_worker.solver import solve_advanced_basket, solve_two_supplier_split


def _offer(
    product_id: object,
    supplier_id: object,
    amount: str,
    currency: str = "GBP",
) -> OfferInput:
    return OfferInput(
        offer_id=uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        quantity="1.000000",
        total_landed_cost=Money(amount=amount, currency=currency),
    )


def test_solver_returns_feasible_minimum_cost_split() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_a, product_b = uuid4(), uuid4()
    result = solve_two_supplier_split(
        supplier_ids=[supplier_a, supplier_b],
        items=[
            BasketItem(workspace_product_id=product_a, quantity="1.000000"),
            BasketItem(workspace_product_id=product_b, quantity="1.000000"),
        ],
        offers=[
            _offer(product_a, supplier_a, "1.0000"),
            _offer(product_a, supplier_b, "5.0000"),
            _offer(product_b, supplier_a, "5.0000"),
            _offer(product_b, supplier_b, "1.0000"),
        ],
    )
    assert result.feasible is True
    assert result.total_landed_cost is not None
    assert result.total_landed_cost.amount == "2.0000"


def test_solver_does_not_force_split_when_single_supplier_is_cheaper() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_a, product_b = uuid4(), uuid4()
    result = solve_two_supplier_split(
        supplier_ids=[supplier_a, supplier_b],
        items=[
            BasketItem(workspace_product_id=product_a, quantity="1.000000"),
            BasketItem(workspace_product_id=product_b, quantity="1.000000"),
        ],
        offers=[
            _offer(product_a, supplier_a, "1.0000"),
            _offer(product_a, supplier_b, "5.0000"),
            _offer(product_b, supplier_a, "1.0000"),
            _offer(product_b, supplier_b, "5.0000"),
        ],
    )
    allocation_by_supplier = {
        allocation.supplier_id: allocation for allocation in result.allocation
    }
    assert len(allocation_by_supplier[supplier_a].lines) == 2
    assert len(allocation_by_supplier[supplier_b].lines) == 0


def test_solver_reports_commercial_infeasibility_as_result_not_exception() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    result = solve_two_supplier_split(
        supplier_ids=[supplier_a, supplier_b],
        items=[BasketItem(workspace_product_id=product_id, quantity="1.000000")],
        offers=[],
    )
    assert result.feasible is False
    assert result.infeasible_items[0].reason == "no_offer_from_named_suppliers"
    assert set(result.infeasible_items[0].missing_supplier_ids) == {supplier_a, supplier_b}


def test_solver_reports_mixed_currency_offers_as_infeasible_without_cost_totals() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_id = uuid4()
    result = solve_two_supplier_split(
        supplier_ids=[supplier_a, supplier_b],
        items=[BasketItem(workspace_product_id=product_id, quantity="1.000000")],
        offers=[
            _offer(product_id, supplier_a, "1.0000", currency="GBP"),
            _offer(product_id, supplier_b, "100.0000", currency="EUR"),
        ],
    )

    assert result.feasible is False
    assert result.infeasible_items[0].reason == "mixed_currency_offers"
    assert result.total_landed_cost is None
    assert result.allocation == []
    assert all(baseline.total_landed_cost is None for baseline in result.single_supplier_baselines)


def test_solver_reports_basket_wide_currency_mixing() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    product_a = UUID("00000000-0000-4000-8000-000000000001")
    product_b = UUID("00000000-0000-4000-8000-000000000002")
    result = solve_two_supplier_split(
        supplier_ids=[supplier_a, supplier_b],
        items=[
            BasketItem(workspace_product_id=product_a, quantity="1.000000"),
            BasketItem(workspace_product_id=product_b, quantity="1.000000"),
        ],
        offers=[
            _offer(product_a, supplier_a, "10.0000", currency="GBP"),
            _offer(product_a, supplier_b, "11.0000", currency="GBP"),
            _offer(product_b, supplier_a, "10.0000", currency="EUR"),
            _offer(product_b, supplier_b, "11.0000", currency="EUR"),
        ],
    )

    assert result.feasible is False
    assert [item.workspace_product_id for item in result.infeasible_items] == [product_b]
    assert result.infeasible_items[0].reason == "mixed_currency_offers"
    assert result.total_landed_cost is None
    assert result.allocation == []


def test_advanced_solver_reports_mixed_currency_and_excludes_offer_from_totals() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    mixed_product, valid_product = uuid4(), uuid4()
    request = AdvancedBasketRequest(
        id=uuid4(),
        tenant_id=uuid4(),
        supplier_ids=[supplier_a, supplier_b],
        items=[
            BasketItem(workspace_product_id=mixed_product, quantity="1.000000"),
            BasketItem(workspace_product_id=valid_product, quantity="1.000000"),
        ],
        hard_constraints=OptimisationHardConstraints(),
        rule_version="advanced-basket-optimiser-v1",
    )
    offers = [
        AdvancedOfferInput(
            offer_id=uuid4(),
            workspace_product_id=mixed_product,
            supplier_id=supplier_a,
            quantity="1.000000",
            total_landed_cost=Money(amount="1.0000", currency="GBP"),
            unit_landed_cost=Money(amount="1.0000", currency="GBP"),
            source_landed_cost_id=uuid4(),
        ),
        AdvancedOfferInput(
            offer_id=uuid4(),
            workspace_product_id=mixed_product,
            supplier_id=supplier_b,
            quantity="1.000000",
            total_landed_cost=Money(amount="100.0000", currency="EUR"),
            unit_landed_cost=Money(amount="100.0000", currency="EUR"),
            source_landed_cost_id=uuid4(),
        ),
        AdvancedOfferInput(
            offer_id=uuid4(),
            workspace_product_id=valid_product,
            supplier_id=supplier_a,
            quantity="1.000000",
            total_landed_cost=Money(amount="7.0000", currency="GBP"),
            unit_landed_cost=Money(amount="7.0000", currency="GBP"),
            source_landed_cost_id=uuid4(),
        ),
        AdvancedOfferInput(
            offer_id=uuid4(),
            workspace_product_id=valid_product,
            supplier_id=supplier_b,
            quantity="1.000000",
            total_landed_cost=Money(amount="8.0000", currency="GBP"),
            unit_landed_cost=Money(amount="8.0000", currency="GBP"),
            source_landed_cost_id=uuid4(),
        ),
    ]
    # Exercise the solver boundary with a malformed upstream snapshot; normal model
    # validation rejects mixed currencies before the solver can report the item.
    payload = AdvancedOptimisationInput.model_construct(
        request=request,
        offers=offers,
        supplier_terms=[],
        supplier_risks=[],
    )

    result = solve_advanced_basket(input_payload=payload)

    mixed_violation = next(
        violation
        for violation in result.violated_constraints
        if violation.kind == "mixed_currency"
    )
    assert mixed_violation.workspace_product_id == mixed_product
    assert result.total_landed_cost == Money(amount="7.0000", currency="GBP")
    assert result.allocation[0].total_landed_cost == Money(amount="7.0000", currency="GBP")
    assert all(
        line.workspace_product_id != mixed_product
        for allocation in result.allocation
        for line in allocation.lines
    )
    assert all(baseline.total_landed_cost is None for baseline in result.single_supplier_baselines)
