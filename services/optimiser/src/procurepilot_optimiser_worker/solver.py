from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from ortools.sat.python import cp_model

from procurepilot_optimiser_worker.models import (
    AdvancedBasketRequest,
    AdvancedBasketResult,
    AdvancedOfferInput,
    AdvancedOptimisationInput,
    AllocatedBasketLine,
    AppliedConstraint,
    BasketItem,
    BasketSplitResult,
    InfeasibleBasketItem,
    Money,
    OfferInput,
    OptimisationConfidence,
    RiskNote,
    SingleSupplierBaseline,
    SupplierAllocation,
    SupplierCommercialTerms,
    SupplierRiskSignal,
    ViolatedConstraint,
)

SOLVER_VERSION = "basket-split-cp-sat-v1"
ADVANCED_SOLVER_VERSION = "advanced-basket-cp-sat-v1"
MONEY_QUANT = Decimal("0.0001")
INT_SCALE = Decimal("10000")


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


def solve_advanced_basket(
    *,
    input_payload: AdvancedOptimisationInput,
    computed_at: datetime | None = None,
) -> AdvancedBasketResult:
    request = input_payload.request
    now = (computed_at or datetime.now(UTC)).replace(microsecond=0)
    valid_until = now
    terms_by_supplier = {terms.supplier_id: terms for terms in input_payload.supplier_terms}
    risks_by_supplier = {risk.supplier_id: risk for risk in input_payload.supplier_risks}
    eligible_supplier_ids = [
        supplier_id
        for supplier_id in sorted(request.supplier_ids)
        if supplier_id not in set(request.hard_constraints.excluded_supplier_ids)
    ]
    currency = _advanced_currency(input_payload.offers, input_payload.supplier_terms)
    offers = _advanced_offers_by_item_supplier(
        request.items,
        input_payload.offers,
        terms_by_supplier,
    )
    applied = _static_applied_constraints(request.hard_constraints.excluded_supplier_ids)
    applied.append(
        AppliedConstraint(
            kind="urgency",
            description="deterministic tie-break by supplier_id, then offer_id",
        )
    )
    applied.extend(_supplier_term_applied_constraints(input_payload.supplier_terms))
    risk_notes = _risk_notes(risks_by_supplier.values())
    max_risk = request.hard_constraints.max_supplier_risk_decimal
    if max_risk is not None:
        eligible_supplier_ids = [
            supplier_id
            for supplier_id in eligible_supplier_ids
            if risks_by_supplier.get(supplier_id) is None
            or risks_by_supplier[supplier_id].risk_score_decimal <= max_risk
        ]

    violations = _candidate_violations(
        request.items,
        request.supplier_ids,
        eligible_supplier_ids,
        offers,
        terms_by_supplier,
        risks_by_supplier,
        max_risk,
    )
    baselines = _advanced_baselines(
        request.supplier_ids,
        request.items,
        offers,
        terms_by_supplier,
        currency,
    )
    if not eligible_supplier_ids or _has_uncovered_item(
        request.items,
        eligible_supplier_ids,
        offers,
    ):
        return _advanced_infeasible_result(
            request=request,
            baselines=baselines,
            applied_constraints=applied,
            violated_constraints=violations,
            risk_notes=risk_notes,
            source_landed_cost_ids=input_payload.offers,
            now=now,
            valid_until=valid_until,
        )

    solved = _minimum_weighted_advanced_assignment(
        request=request,
        supplier_ids=eligible_supplier_ids,
        offers=offers,
        terms_by_supplier=terms_by_supplier,
        risks_by_supplier=risks_by_supplier,
    )
    if solved is None:
        return _advanced_infeasible_result(
            request=request,
            baselines=baselines,
            applied_constraints=applied,
            violated_constraints=violations,
            risk_notes=risk_notes,
            source_landed_cost_ids=input_payload.offers,
            now=now,
            valid_until=valid_until,
        )

    chosen, fee_by_supplier = solved
    allocations, total, chosen_applied = _advanced_allocations(
        request.items,
        chosen,
        offers,
        terms_by_supplier,
        fee_by_supplier,
        currency,
    )
    applied.extend(chosen_applied)
    return AdvancedBasketResult(
        feasible=True,
        allocation=allocations,
        total_landed_cost=_money(total, currency),
        single_supplier_baselines=baselines,
        applied_constraints=applied,
        violated_constraints=violations,
        risk_notes=risk_notes,
        confidence=_confidence(input_payload.supplier_risks),
        valid_until=valid_until,
        source_landed_cost_ids=sorted(
            {offer.source_landed_cost_id for offer in input_payload.offers}
        ),
        solver_version=ADVANCED_SOLVER_VERSION,
        rule_version=request.rule_version,
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


def _minimum_weighted_advanced_assignment(
    *,
    request: AdvancedBasketRequest,
    supplier_ids: list[UUID],
    offers: dict[tuple[UUID, UUID], AdvancedOfferInput],
    terms_by_supplier: dict[UUID, SupplierCommercialTerms],
    risks_by_supplier: dict[UUID, SupplierRiskSignal],
) -> tuple[dict[UUID, UUID], dict[UUID, Decimal]] | None:
    model = cp_model.CpModel()
    choices: dict[tuple[UUID, UUID], cp_model.IntVar] = {}
    used: dict[UUID, cp_model.IntVar] = {}
    fee_applies: dict[UUID, cp_model.IntVar] = {}
    subtotal_vars: dict[UUID, cp_model.LinearExpr] = {}
    for supplier_id in supplier_ids:
        used[supplier_id] = model.NewBoolVar(f"used_{supplier_id}")
    for item in request.items:
        vars_for_item = []
        for supplier_id in supplier_ids:
            if (item.workspace_product_id, supplier_id) not in offers:
                continue
            var = model.NewBoolVar(f"x_{item.workspace_product_id}_{supplier_id}")
            choices[(item.workspace_product_id, supplier_id)] = var
            vars_for_item.append(var)
            model.AddImplication(var, used[supplier_id])
        if not vars_for_item:
            return None
        model.Add(sum(vars_for_item) == 1)
    for supplier_id in supplier_ids:
        supplier_choices = [
            var for (_product_id, chosen_supplier_id), var in choices.items()
            if chosen_supplier_id == supplier_id
        ]
        model.Add(sum(supplier_choices) >= used[supplier_id])
        model.Add(sum(supplier_choices) <= len(supplier_choices) * used[supplier_id])
        subtotal = sum(
            _money_int(offers[(product_id, supplier_id)].amount) * var
            for (product_id, chosen_supplier_id), var in choices.items()
            if chosen_supplier_id == supplier_id
        )
        subtotal_vars[supplier_id] = subtotal
        terms = terms_by_supplier.get(supplier_id)
        if terms is not None and terms.minimum_order_value is not None:
            model.Add(
                subtotal >= _money_int(Decimal(terms.minimum_order_value.amount))
            ).OnlyEnforceIf(used[supplier_id])
        fee_applies[supplier_id] = _delivery_fee_var(
            model,
            supplier_id,
            used[supplier_id],
            subtotal,
            terms,
        )
    objective_terms = []
    for (product_id, supplier_id), var in choices.items():
        offer = offers[(product_id, supplier_id)]
        objective_terms.append(
            _weighted_offer_cost(
                request=request,
                offer=offer,
                supplier_id=supplier_id,
                risk=risks_by_supplier.get(supplier_id),
                tie_rank=sorted(request.supplier_ids).index(supplier_id),
            )
            * var
        )
    for supplier_id, var in fee_applies.items():
        terms = terms_by_supplier.get(supplier_id)
        if terms is not None and terms.delivery_fee is not None:
            objective_terms.append(_weighted_delivery_fee(request, terms) * var)
    model.Minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return None
    chosen: dict[UUID, UUID] = {}
    for item in request.items:
        for supplier_id in supplier_ids:
            var = choices.get((item.workspace_product_id, supplier_id))
            if var is not None and solver.Value(var) == 1:
                chosen[item.workspace_product_id] = supplier_id
    fees: dict[UUID, Decimal] = {}
    for supplier_id, var in fee_applies.items():
        terms = terms_by_supplier.get(supplier_id)
        if (
            terms is not None
            and terms.delivery_fee is not None
            and solver.Value(var) == 1
        ):
            fees[supplier_id] = Decimal(terms.delivery_fee.amount)
    return chosen, fees


def _delivery_fee_var(
    model: cp_model.CpModel,
    supplier_id: UUID,
    used: cp_model.IntVar,
    subtotal: cp_model.LinearExpr,
    terms: SupplierCommercialTerms | None,
) -> cp_model.IntVar:
    fee = model.NewBoolVar(f"delivery_fee_{supplier_id}")
    if terms is None or terms.delivery_fee is None:
        model.Add(fee == 0)
        return fee
    if terms.free_delivery_threshold is None:
        model.Add(fee == used)
        return fee
    above_threshold = model.NewBoolVar(f"free_delivery_{supplier_id}")
    threshold = _money_int(Decimal(terms.free_delivery_threshold.amount))
    model.Add(subtotal >= threshold).OnlyEnforceIf(above_threshold)
    model.Add(subtotal <= threshold - 1).OnlyEnforceIf(above_threshold.Not())
    model.AddImplication(fee, used)
    model.AddImplication(fee, above_threshold.Not())
    model.AddBoolOr([used.Not(), above_threshold, fee])
    return fee


def _advanced_offers_by_item_supplier(
    items: list[BasketItem],
    offers: list[AdvancedOfferInput],
    terms_by_supplier: dict[UUID, SupplierCommercialTerms],
) -> dict[tuple[UUID, UUID], AdvancedOfferInput]:
    requested_quantities = {
        item.workspace_product_id: item.quantity_decimal for item in items
    }
    adjusted = {}
    for offer in offers:
        quantity = requested_quantities.get(offer.workspace_product_id, Decimal(offer.quantity))
        adjusted[(offer.workspace_product_id, offer.supplier_id)] = _tier_adjusted_offer(
            offer,
            quantity,
            terms_by_supplier.get(offer.supplier_id),
        )
    return adjusted


def _tier_adjusted_offer(
    offer: AdvancedOfferInput,
    requested_quantity: Decimal,
    terms: SupplierCommercialTerms | None,
) -> AdvancedOfferInput:
    if terms is None:
        return offer
    matching_tiers = [
        tier for tier in terms.quantity_tiers
        if tier.min_quantity_decimal <= requested_quantity
        and (
            tier.workspace_product_id is None
            or tier.workspace_product_id == offer.workspace_product_id
        )
    ]
    if not matching_tiers:
        return offer
    tier = max(matching_tiers, key=lambda value: value.min_quantity_decimal)
    amount = requested_quantity * Decimal(tier.unit_price.amount)
    return offer.model_copy(
        update={
            "total_landed_cost": _money(amount, tier.unit_price.currency),
            "unit_landed_cost": tier.unit_price,
        }
    )


def _weighted_offer_cost(
    *,
    request: AdvancedBasketRequest,
    offer: AdvancedOfferInput,
    supplier_id: UUID,
    risk: SupplierRiskSignal | None,
    tie_rank: int,
) -> int:
    weights = request.soft_weights
    price = Decimal(weights.price_competitiveness) * Decimal(_money_int(offer.amount))
    preferred = Decimal("0") if offer.preferred else Decimal(weights.preferred_supplier) * 10000
    risk_cost = (
        (risk.risk_score_decimal if risk is not None else Decimal("0.5000"))
        * Decimal(weights.risk)
        * 10000
    )
    lead_time = Decimal(offer.lead_time_days or 0) * Decimal(weights.lead_time) * 100
    quality = Decimal(weights.quality) * (
        Decimal("5000") if risk is not None and risk.insufficient_evidence else Decimal("0")
    )
    return int(price + preferred + risk_cost + lead_time + quality) * 1000 + tie_rank


def _weighted_delivery_fee(
    request: AdvancedBasketRequest,
    terms: SupplierCommercialTerms,
) -> int:
    if terms.delivery_fee is None:
        return 0
    return int(
        Decimal(request.soft_weights.price_competitiveness)
        * Decimal(_money_int(Decimal(terms.delivery_fee.amount)))
    ) * 1000


def _advanced_allocations(
    items: list[BasketItem],
    chosen: dict[UUID, UUID],
    offers: dict[tuple[UUID, UUID], AdvancedOfferInput],
    terms_by_supplier: dict[UUID, SupplierCommercialTerms],
    fee_by_supplier: dict[UUID, Decimal],
    currency: str,
) -> tuple[list[SupplierAllocation], Decimal, list[AppliedConstraint]]:
    allocations: dict[UUID, list[AllocatedBasketLine]] = defaultdict(list)
    totals: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    applied: list[AppliedConstraint] = []
    for item in items:
        supplier_id = chosen[item.workspace_product_id]
        offer = offers[(item.workspace_product_id, supplier_id)]
        totals[supplier_id] += offer.amount
        allocations[supplier_id].append(
            AllocatedBasketLine(
                workspace_product_id=item.workspace_product_id,
                quantity=item.quantity,
                offer_id=offer.offer_id,
                landed_cost=offer.total_landed_cost,
            )
        )
        _append_tier_constraint(applied, item, supplier_id, terms_by_supplier.get(supplier_id))
    for supplier_id, fee in fee_by_supplier.items():
        totals[supplier_id] += fee
        applied.append(
            AppliedConstraint(
                kind="delivery_fee",
                supplier_id=supplier_id,
                description="delivery fee applied below free-delivery threshold",
            )
        )
    for supplier_id, terms in terms_by_supplier.items():
        if terms.free_delivery_threshold is not None and totals.get(supplier_id, 0) >= Decimal(
            terms.free_delivery_threshold.amount
        ):
            applied.append(
                AppliedConstraint(
                    kind="free_delivery_threshold",
                    supplier_id=supplier_id,
                    description="free-delivery threshold met",
                )
            )
    supplier_allocations = [
        SupplierAllocation(
            supplier_id=supplier_id,
            lines=allocations[supplier_id],
            total_landed_cost=_money(totals[supplier_id], currency),
        )
        for supplier_id in sorted(allocations)
    ]
    total = sum(totals.values(), Decimal("0.0000"))
    return supplier_allocations, total, applied


def _append_tier_constraint(
    applied: list[AppliedConstraint],
    item: BasketItem,
    supplier_id: UUID,
    terms: SupplierCommercialTerms | None,
) -> None:
    if terms is None:
        return
    matching = [
        tier for tier in terms.quantity_tiers
        if tier.min_quantity_decimal <= item.quantity_decimal
        and (
            tier.workspace_product_id is None
            or tier.workspace_product_id == item.workspace_product_id
        )
    ]
    if not matching:
        return
    tier = max(matching, key=lambda value: value.min_quantity_decimal)
    applied.append(
        AppliedConstraint(
            kind="quantity_tier",
            supplier_id=supplier_id,
            workspace_product_id=item.workspace_product_id,
            description=f"quantity tier applied at {tier.min_quantity} units",
            source_ids=[tier.source_term_id] if tier.source_term_id is not None else [],
        )
    )


def _candidate_violations(
    items: list[BasketItem],
    supplier_ids: list[UUID],
    eligible_supplier_ids: list[UUID],
    offers: dict[tuple[UUID, UUID], AdvancedOfferInput],
    terms_by_supplier: dict[UUID, SupplierCommercialTerms],
    risks_by_supplier: dict[UUID, SupplierRiskSignal],
    max_risk: Decimal | None,
) -> list[ViolatedConstraint]:
    violations = []
    eligible = set(eligible_supplier_ids)
    for item in items:
        any_selected_offer = any(
            (item.workspace_product_id, supplier_id) in offers for supplier_id in supplier_ids
        )
        any_eligible_offer = any(
            (item.workspace_product_id, supplier_id) in offers for supplier_id in eligible
        )
        if not any_selected_offer or (eligible and not any_eligible_offer):
            violations.append(
                ViolatedConstraint(
                    kind="no_eligible_supplier",
                    workspace_product_id=item.workspace_product_id,
                    requested_quantity=item.quantity,
                    message="no eligible supplier has a current offer for this item",
                )
            )
    for supplier_id in supplier_ids:
        terms = terms_by_supplier.get(supplier_id)
        subtotal = sum(
            offer.amount for (_product_id, offer_supplier_id), offer in offers.items()
            if offer_supplier_id == supplier_id
        )
        if (
            terms is not None
            and terms.minimum_order_value is not None
            and subtotal < Decimal(terms.minimum_order_value.amount)
        ):
            violations.append(
                ViolatedConstraint(
                    kind="minimum_order_value",
                    supplier_id=supplier_id,
                    message="supplier current eligible lines do not meet minimum order value",
                )
            )
        risk = risks_by_supplier.get(supplier_id)
        if max_risk is not None and risk is not None and risk.risk_score_decimal > max_risk:
            violations.append(
                ViolatedConstraint(
                    kind="risk_tolerance",
                    supplier_id=supplier_id,
                    message="supplier risk score exceeds requested tolerance",
                    source_ids=risk.source_ids,
                )
            )
    return violations


def _advanced_baselines(
    supplier_ids: list[UUID],
    items: list[BasketItem],
    offers: dict[tuple[UUID, UUID], AdvancedOfferInput],
    terms_by_supplier: dict[UUID, SupplierCommercialTerms],
    currency: str,
) -> list[SingleSupplierBaseline]:
    baselines = []
    for supplier_id in sorted(supplier_ids):
        supplier_offers = [offers.get((item.workspace_product_id, supplier_id)) for item in items]
        feasible = all(offer is not None for offer in supplier_offers)
        total = sum((offer.amount for offer in supplier_offers if offer), Decimal("0.0000"))
        terms = terms_by_supplier.get(supplier_id)
        if feasible and terms is not None and terms.minimum_order_value is not None:
            feasible = total >= Decimal(terms.minimum_order_value.amount)
        baselines.append(
            SingleSupplierBaseline(
                supplier_id=supplier_id,
                feasible=feasible,
                total_landed_cost=_money(total, currency) if feasible else None,
            )
        )
    return baselines


def _advanced_infeasible_result(
    *,
    request: AdvancedBasketRequest,
    baselines: list[SingleSupplierBaseline],
    applied_constraints: list[AppliedConstraint],
    violated_constraints: list[ViolatedConstraint],
    risk_notes: list[RiskNote],
    source_landed_cost_ids: list[AdvancedOfferInput],
    now: datetime,
    valid_until: datetime,
) -> AdvancedBasketResult:
    return AdvancedBasketResult(
        feasible=False,
        allocation=[],
        total_landed_cost=None,
        single_supplier_baselines=baselines,
        applied_constraints=applied_constraints,
        violated_constraints=violated_constraints,
        risk_notes=risk_notes,
        confidence=OptimisationConfidence(
            score="0.5000",
            insufficient_evidence=True,
            reasons=["business constraints made the basket infeasible"],
        ),
        valid_until=valid_until,
        source_landed_cost_ids=sorted(
            {offer.source_landed_cost_id for offer in source_landed_cost_ids}
        ),
        solver_version=ADVANCED_SOLVER_VERSION,
        rule_version=request.rule_version,
        computed_at=now,
    )


def _risk_notes(risks: Iterable[SupplierRiskSignal]) -> list[RiskNote]:
    notes = []
    for risk in risks:
        severity = "high" if risk.risk_score_decimal >= Decimal("0.7500") else "medium"
        if risk.risk_score_decimal < Decimal("0.5000") and not risk.insufficient_evidence:
            severity = "low"
        notes.append(
            RiskNote(
                supplier_id=risk.supplier_id,
                severity=severity,
                message="supplier risk signal included in optimisation",
                confidence=risk.confidence,
                source_ids=risk.source_ids,
            )
        )
    return notes


def _confidence(risks: list[SupplierRiskSignal]) -> OptimisationConfidence:
    insufficient = any(risk.insufficient_evidence for risk in risks)
    return OptimisationConfidence(
        score="0.7000" if insufficient else "0.9000",
        insufficient_evidence=insufficient,
        reasons=["current offers, supplier terms, and risk signals evaluated"],
    )


def _static_applied_constraints(excluded_supplier_ids: list[UUID]) -> list[AppliedConstraint]:
    return [
        AppliedConstraint(
            kind="supplier_exclusion",
            supplier_id=supplier_id,
            description="supplier excluded by requester",
        )
        for supplier_id in excluded_supplier_ids
    ]


def _supplier_term_applied_constraints(
    supplier_terms: list[SupplierCommercialTerms],
) -> list[AppliedConstraint]:
    applied: list[AppliedConstraint] = []
    for terms in supplier_terms:
        for money, kind, description in (
            (
                terms.minimum_order_value,
                "minimum_order_value",
                "minimum order value considered",
            ),
            (terms.delivery_fee, "delivery_fee", "delivery fee considered"),
            (
                terms.free_delivery_threshold,
                "free_delivery_threshold",
                "free-delivery threshold considered",
            ),
        ):
            if money is not None:
                applied.append(
                    AppliedConstraint(
                        kind=kind,
                        supplier_id=terms.supplier_id,
                        description=description,
                    )
                )
        for tier in terms.quantity_tiers:
            applied.append(
                AppliedConstraint(
                    kind="quantity_tier",
                    supplier_id=terms.supplier_id,
                    workspace_product_id=tier.workspace_product_id,
                    description="quantity tier considered",
                    source_ids=[tier.source_term_id] if tier.source_term_id is not None else [],
                )
            )
    return applied


def _has_uncovered_item(
    items: list[BasketItem],
    supplier_ids: list[UUID],
    offers: dict[tuple[UUID, UUID], AdvancedOfferInput],
) -> bool:
    return any(
        not any((item.workspace_product_id, supplier_id) in offers for supplier_id in supplier_ids)
        for item in items
    )


def _advanced_currency(
    offers: list[AdvancedOfferInput],
    terms: list[SupplierCommercialTerms],
) -> str:
    for offer in offers:
        return offer.total_landed_cost.currency
    for supplier_terms in terms:
        for money in (
            supplier_terms.minimum_order_value,
            supplier_terms.delivery_fee,
            supplier_terms.free_delivery_threshold,
        ):
            if money is not None:
                return money.currency
    return "GBP"


def _money_int(amount: Decimal) -> int:
    return int((amount * INT_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


def _money(amount: Decimal, currency: str) -> Money:
    return Money(
        amount=format(amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP), "f"),
        currency=currency,
    )
