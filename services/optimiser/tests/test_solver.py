from __future__ import annotations

from uuid import uuid4

from procurepilot_optimiser_worker.models import BasketItem, Money, OfferInput
from procurepilot_optimiser_worker.solver import solve_two_supplier_split


def _offer(product_id: object, supplier_id: object, amount: str) -> OfferInput:
    return OfferInput(
        offer_id=uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        quantity="1.000000",
        total_landed_cost=Money(amount=amount, currency="GBP"),
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
