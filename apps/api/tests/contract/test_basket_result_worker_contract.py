"""Real services/optimiser output must read back through the API's BasketSplitJob.

The worker and the API define their result models independently (separate deployables), so a
silent drift turns ``GET /baskets/{id}`` into a 500 for a job that completed fine. These tests
run results produced by the actual solver through ``basket_service._job``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

pytest.importorskip("procurepilot_optimiser_worker")
pytest.importorskip("ortools")

from procurepilot_optimiser_worker.models import (  # noqa: E402
    AdvancedBasketRequest,
    AdvancedOfferInput,
    AdvancedOptimisationInput,
    BasketItem,
    Money,
    OptimisationHardConstraints,
    SupplierRiskSignal,
)
from procurepilot_optimiser_worker.solver import solve_advanced_basket  # noqa: E402

from procurepilot_api.modules.offers.basket_service import _job  # noqa: E402
from procurepilot_api.modules.offers.schemas import AdvancedBasketResult  # noqa: E402


def _money(amount: str) -> Money:
    return Money(amount=amount, currency="EGP")


def _offer(product_id, supplier_id, total: str) -> AdvancedOfferInput:  # noqa: ANN001
    return AdvancedOfferInput(
        offer_id=uuid4(),
        workspace_product_id=product_id,
        supplier_id=supplier_id,
        quantity="1.000000",
        total_landed_cost=_money(total),
        unit_landed_cost=_money(total),
        source_landed_cost_id=uuid4(),
    )


def _risk(supplier_id, score: str) -> SupplierRiskSignal:  # noqa: ANN001
    return SupplierRiskSignal(
        supplier_id=supplier_id,
        risk_score=score,
        confidence="0.9000",
        insufficient_evidence=False,
        source_ids=[uuid4()],
        rule_version="supplier-risk-v1",
    )


def _row(result: dict[str, object], suppliers: list, items: list[BasketItem]) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": uuid4(),
        "supplier_ids": suppliers,
        "items": [i.model_dump(mode="json") for i in items],
        "status": "completed",
        "result": result,
        "error": None,
        "created_at": datetime.now(UTC),
        "started_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
    }


def _solve(*, excluded: list | None = None, offer_for_second: bool = True):  # noqa: ANN202
    s1, s2, p1, p2 = uuid4(), uuid4(), uuid4(), uuid4()
    items = [
        BasketItem(workspace_product_id=p1, quantity="1.000000"),
        BasketItem(workspace_product_id=p2, quantity="1.000000"),
    ]
    offers = [_offer(p1, s1, "10.0000"), _offer(p1, s2, "12.0000"), _offer(p2, s2, "5.0000")]
    if not offer_for_second:
        offers = offers[:2]
    request = AdvancedBasketRequest(
        id=uuid4(),
        tenant_id=uuid4(),
        supplier_ids=[s1, s2],
        items=items,
        hard_constraints=OptimisationHardConstraints(excluded_supplier_ids=excluded or []),
        rule_version="advanced-basket-v1",
    )
    result = solve_advanced_basket(
        input_payload=AdvancedOptimisationInput(
            request=request,
            offers=offers,
            supplier_risks=[_risk(s1, "0.8000"), _risk(s2, "0.2000")],
        )
    )
    return _row(result.model_dump(mode="json"), [s1, s2], items), s1


def test_feasible_worker_result_reads_back_with_api_shape() -> None:
    row, _ = _solve()
    job = _job(row)

    assert isinstance(job.result, AdvancedBasketResult)
    assert job.result.feasible is True
    assert job.result.confidence in ("high", "medium", "low")
    for allocation in job.result.allocation:
        assert all(line.supplier_id == allocation.supplier_id for line in allocation.lines)
    assert "high_supplier_risk" in job.result.risk_notes


def test_infeasible_worker_result_reads_back() -> None:
    row, _ = _solve(offer_for_second=False)
    job = _job(row)

    assert isinstance(job.result, AdvancedBasketResult)
    assert job.result.feasible is False
    assert job.result.violated_constraints
    assert all(v.reason and v.description for v in job.result.violated_constraints)


def test_excluded_supplier_worker_result_reads_back() -> None:
    row, s1 = _solve()
    row2, _ = _solve()
    result = row2["result"]
    result["applied_constraints"].append(  # type: ignore[index]
        {"kind": "supplier_exclusion", "supplier_id": str(s1), "description": "x", "source_ids": []}
    )
    assert isinstance(_job(row2).result, AdvancedBasketResult)


def test_legacy_stored_row_with_worker_shape_does_not_500() -> None:
    row, _ = _solve()
    result = row["result"]
    assert isinstance(result["confidence"], dict)  # type: ignore[index]  # the drifted shape
    assert "advisory_only" in result  # type: ignore[operator]
    job = _job(row)
    assert job.status == "completed" and job.result is not None


def test_solver_tie_break_is_not_exposed_as_an_applied_constraint() -> None:
    row, _ = _solve()
    applied = row["result"]["applied_constraints"]  # type: ignore[index]
    assert any("tie-break" in c["description"] for c in applied), "worker still emits it"

    job = _job(row)

    assert isinstance(job.result, AdvancedBasketResult)
    assert not any("tie-break" in c.description for c in job.result.applied_constraints)


def test_infeasible_items_are_synthesised_from_per_item_violations() -> None:
    row, _ = _solve(offer_for_second=False)
    missing_product = next(
        v["workspace_product_id"]
        for v in row["result"]["violated_constraints"]  # type: ignore[index]
        if v["kind"] == "no_eligible_supplier"
    )

    job = _job(row)

    assert isinstance(job.result, AdvancedBasketResult)
    assert [str(i.workspace_product_id) for i in job.result.infeasible_items] == [missing_product]
    item = job.result.infeasible_items[0]
    assert item.reason == "no_offer_from_named_suppliers"
    assert item.missing_supplier_ids == row["supplier_ids"]


def test_job_exposes_the_pack_snapshot_stored_at_submission() -> None:
    row, _ = _solve()
    product_id = str(uuid4())
    row["request_snapshot"] = {
        "pack_snapshot": {product_id: {"base_quantity": "0.5", "base_unit": "kilogram"}}
    }

    job = _job(row)

    assert job.pack_snapshot is not None
    assert job.pack_snapshot[product_id].base_quantity == "0.5"
