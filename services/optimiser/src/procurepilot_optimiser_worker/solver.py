from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from ortools.sat.python import cp_model

from procurepilot_optimiser_worker.models import (
    AllocatedBasketLine,
    BasketItem,
    BasketSplitResult,
    InfeasibleBasketItem,
    Money,
    OfferInput,
    SingleSupplierBaseline,
    SupplierAllocation,
)

SOLVER_VERSION = "basket-split-cp-sat-v1"
MONEY_QUANT = Decimal("0.0001")


def solve_two_supplier_split(
    *,
    supplier_ids: list[UUID],
    items: list[BasketItem],
    offers: list[OfferInput],
    computed_at: datetime | None = None,
) -> BasketSplitResult:
    by_product_supplier = {
        (offer.workspace_product_id, offer.supplier_id): offer for offer in offers
    }
    infeasible = _infeasible_items(supplier_ids, items, by_product_supplier)
    baselines = _baselines(supplier_ids, items, by_product_supplier)
    now = computed_at or datetime.now(UTC)
    if infeasible:
        return BasketSplitResult(
            feasible=False,
            allocation=[],
            total_landed_cost=None,
            single_supplier_baselines=baselines,
            infeasible_items=infeasible,
            solver_version=SOLVER_VERSION,
            computed_at=now,
        )

    chosen = _minimum_cost_assignment(supplier_ids, items, by_product_supplier)
    allocations: dict[UUID, list[AllocatedBasketLine]] = defaultdict(list)
    totals: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    currency = None
    for item in items:
        supplier_id = chosen[item.workspace_product_id]
        offer = by_product_supplier[(item.workspace_product_id, supplier_id)]
        currency = offer.total_landed_cost.currency if currency is None else currency
        totals[supplier_id] += offer.amount
        allocations[supplier_id].append(
            AllocatedBasketLine(
                workspace_product_id=item.workspace_product_id,
                quantity=item.quantity,
                offer_id=offer.offer_id,
                landed_cost=offer.total_landed_cost,
            )
        )
    total = sum(totals.values(), Decimal("0.0000")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return BasketSplitResult(
        feasible=True,
        allocation=[
            SupplierAllocation(
                supplier_id=supplier_id,
                lines=allocations.get(supplier_id, []),
                total_landed_cost=_money(
                    totals.get(supplier_id, Decimal("0.0000")),
                    currency or "GBP",
                ),
            )
            for supplier_id in supplier_ids
        ],
        total_landed_cost=_money(total, currency or "GBP"),
        single_supplier_baselines=baselines,
        infeasible_items=[],
        solver_version=SOLVER_VERSION,
        computed_at=now,
    )


def _minimum_cost_assignment(
    supplier_ids: list[UUID],
    items: list[BasketItem],
    offers: dict[tuple[UUID, UUID], OfferInput],
) -> dict[UUID, UUID]:
    model = cp_model.CpModel()
    choices: dict[tuple[UUID, UUID], cp_model.IntVar] = {}
    for item in items:
        vars_for_item = []
        for supplier_id in supplier_ids:
            if (item.workspace_product_id, supplier_id) not in offers:
                continue
            var = model.NewBoolVar(f"x_{item.workspace_product_id}_{supplier_id}")
            choices[(item.workspace_product_id, supplier_id)] = var
            vars_for_item.append(var)
        model.Add(sum(vars_for_item) == 1)
    objective_terms = []
    for (product_id, supplier_id), var in choices.items():
        amount_cents = int(
            (offers[(product_id, supplier_id)].amount * Decimal("10000")).to_integral_value()
        )
        objective_terms.append(amount_cents * var)
    model.Minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        raise RuntimeError("basket split solver did not find a feasible assignment")
    result: dict[UUID, UUID] = {}
    for item in items:
        for supplier_id in supplier_ids:
            var = choices.get((item.workspace_product_id, supplier_id))
            if var is not None and solver.Value(var) == 1:
                result[item.workspace_product_id] = supplier_id
    return result


def _infeasible_items(
    supplier_ids: list[UUID],
    items: list[BasketItem],
    offers: dict[tuple[UUID, UUID], OfferInput],
) -> list[InfeasibleBasketItem]:
    blocked = []
    for item in items:
        missing = [
            supplier_id
            for supplier_id in supplier_ids
            if (item.workspace_product_id, supplier_id) not in offers
        ]
        if len(missing) == len(supplier_ids):
            blocked.append(
                InfeasibleBasketItem(
                    workspace_product_id=item.workspace_product_id,
                    requested_quantity=item.quantity,
                    reason="no_offer_from_named_suppliers",
                    missing_supplier_ids=missing,
                )
            )
    return blocked


def _baselines(
    supplier_ids: list[UUID],
    items: list[BasketItem],
    offers: dict[tuple[UUID, UUID], OfferInput],
) -> list[SingleSupplierBaseline]:
    baselines = []
    for supplier_id in supplier_ids:
        supplier_offers = [
            offers.get((item.workspace_product_id, supplier_id))
            for item in items
        ]
        feasible = all(offer is not None for offer in supplier_offers)
        currency = next(
            (offer.total_landed_cost.currency for offer in supplier_offers if offer),
            "GBP",
        )
        total = (
            _money(
                sum((offer.amount for offer in supplier_offers if offer), Decimal("0.0000")),
                currency,
            )
            if feasible
            else None
        )
        baselines.append(
            SingleSupplierBaseline(
                supplier_id=supplier_id,
                feasible=feasible,
                total_landed_cost=total,
            )
        )
    return baselines


def _money(amount: Decimal, currency: str) -> Money:
    return Money(
        amount=format(amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP), "f"),
        currency=currency,
    )
