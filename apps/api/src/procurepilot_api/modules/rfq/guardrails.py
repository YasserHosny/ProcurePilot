from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

GUARDRAIL_VERSION: str = "rfq-guardrail-v1"


@dataclass
class GuardrailCandidateLine:
    workspace_product_id: UUID
    unit_price_amount: Decimal


@dataclass
class GuardrailCandidate:
    rfq_response_id: UUID
    supplier_id: UUID
    currency: str
    total_amount: Decimal
    all_lines_matched: bool
    matched_lines: list[GuardrailCandidateLine]
    captured_at: datetime | None = None
    response_state: str = "active"


@dataclass
class AutoPreparationGuardrail:
    id: UUID
    tenant_id: UUID
    enabled: bool
    min_response_count: int
    max_order_value_amount: Decimal
    max_order_value_currency: str
    max_price_variance_pct: Decimal
    supplier_allowlist: list[UUID] | None
    category_allowlist: list[str] | None
    default_branch_id: UUID
    created_by_membership_id: UUID
    created_at: datetime | None = None


@dataclass
class GuardrailEvaluationInput:
    guardrail: AutoPreparationGuardrail
    rfq_status: str
    total_response_count: int
    candidates: list[GuardrailCandidate]
    recent_average_price_by_product: dict[UUID, Decimal]


@dataclass
class GuardrailDecision:
    fired: bool
    reason: str
    winning_response_id: UUID | None
    guardrail_version: str = GUARDRAIL_VERSION


@dataclass(frozen=True)
class GuardrailExplanation:
    guardrail_id: UUID
    fired: bool
    reason: str


def _evaluate_candidate(
    candidate: GuardrailCandidate,
    guardrail: AutoPreparationGuardrail,
    baseline: dict[UUID, Decimal],
) -> str | None:
    if not candidate.all_lines_matched:
        return "partial_line_response"
    if candidate.currency != guardrail.max_order_value_currency:
        return "currency_mismatch"
    if guardrail.supplier_allowlist is not None and len(guardrail.supplier_allowlist) > 0:
        if candidate.supplier_id not in guardrail.supplier_allowlist:
            return "supplier_not_allowed"
    if guardrail.category_allowlist is not None and len(guardrail.category_allowlist) > 0:
        return "category_allowlist_unsupported"
    if candidate.total_amount > guardrail.max_order_value_amount:
        return "exceeds_max_order_value"

    for line in candidate.matched_lines:
        if line.workspace_product_id not in baseline:
            return "no_price_history_baseline"
        base_price = baseline[line.workspace_product_id]
        if base_price == Decimal("0"):
            return "no_price_history_baseline"
        variance = abs(line.unit_price_amount - base_price) / base_price
        if variance > guardrail.max_price_variance_pct:
            return "price_variance_exceeded"

    return None


def evaluate_guardrail(input: GuardrailEvaluationInput) -> GuardrailDecision:
    if not input.guardrail.enabled:
        return GuardrailDecision(fired=False, reason="guardrail_disabled", winning_response_id=None)

    if input.rfq_status not in ("sent", "responded"):
        return GuardrailDecision(fired=False, reason="rfq_not_open", winning_response_id=None)

    if input.total_response_count < input.guardrail.min_response_count:
        return GuardrailDecision(
            fired=False, reason="min_response_count_not_met", winning_response_id=None
        )

    eligible_candidates = []
    reasons = []

    for candidate in input.candidates:
        if (
            candidate.captured_at is not None
            and input.guardrail.created_at is not None
            and candidate.captured_at < input.guardrail.created_at
        ):
            reasons.append("captured_before_guardrail")
            continue
        reason = _evaluate_candidate(
            candidate, input.guardrail, input.recent_average_price_by_product
        )
        if reason is None:
            eligible_candidates.append(candidate)
        else:
            reasons.append(reason)

    if not eligible_candidates:
        if len(input.candidates) == 1:
            return GuardrailDecision(fired=False, reason=reasons[0], winning_response_id=None)
        return GuardrailDecision(
            fired=False, reason="no_eligible_response", winning_response_id=None
        )

    min_amount = min(c.total_amount for c in eligible_candidates)
    tied_candidates = [c for c in eligible_candidates if c.total_amount == min_amount]

    if len(tied_candidates) > 1:
        return GuardrailDecision(fired=False, reason="tied_responses", winning_response_id=None)

    winning = tied_candidates[0]
    return GuardrailDecision(
        fired=True, reason="guardrail_fired", winning_response_id=winning.rfq_response_id
    )


def explain_guardrail_evaluations(
    *,
    guardrails: list[AutoPreparationGuardrail],
    rfq_status: str,
    total_response_count: int,
    candidates: list[GuardrailCandidate],
    recent_average_price_by_product: dict[UUID, Decimal],
    response_id: UUID,
    responses_pending: bool = False,
    fired_guardrail_ids: set[UUID] | None = None,
) -> list[GuardrailExplanation]:
    """Explain every enabled guardrail for one response without touching the database.

    The ordering here is deliberate: RFQ-wide blockers hide candidate details, then the
    selected response's own data is explained, and only then do we compare it with its
    eligible peers.
    """
    fired_ids = fired_guardrail_ids or set()
    candidate = next((item for item in candidates if item.rfq_response_id == response_id), None)
    explanations: list[GuardrailExplanation] = []

    def eligible_for_guardrail(guardrail: AutoPreparationGuardrail) -> list[GuardrailCandidate]:
        return [
            item
            for item in candidates
            if item.response_state == "active"
            and not (
                item.captured_at is not None
                and guardrail.created_at is not None
                and item.captured_at < guardrail.created_at
            )
        ]

    independent_decisions = {
        guardrail.id: evaluate_guardrail(
            GuardrailEvaluationInput(
                guardrail=guardrail,
                rfq_status=rfq_status,
                total_response_count=total_response_count,
                candidates=eligible_for_guardrail(guardrail),
                recent_average_price_by_product=recent_average_price_by_product,
            )
        )
        for guardrail in guardrails
        if guardrail.enabled
    }
    ambiguous_guardrail_ids = {
        guardrail_id
        for guardrail_id, decision in independent_decisions.items()
        if decision.fired
    }
    if len(ambiguous_guardrail_ids) <= 1:
        ambiguous_guardrail_ids = set()

    for guardrail in guardrails:
        if guardrail.id in fired_ids:
            explanations.append(GuardrailExplanation(guardrail.id, True, "fired"))
            continue
        if rfq_status not in ("sent", "responded"):
            reason = "rfq_not_open"
        elif total_response_count < guardrail.min_response_count:
            reason = "min_response_count_not_met"
        elif responses_pending:
            reason = "responses_pending"
        elif candidate is None:
            reason = "no_eligible_response"
        elif candidate.response_state == "archived":
            reason = "response_archived"
        elif candidate.response_state == "refused":
            reason = "response_refused"
        elif (
            candidate.captured_at is not None
            and guardrail.created_at is not None
            and candidate.captured_at < guardrail.created_at
        ):
            reason = "captured_before_guardrail"
        else:
            candidate_reason = _evaluate_candidate(
                candidate, guardrail, recent_average_price_by_product
            )
            if candidate_reason is not None:
                reason = candidate_reason
            else:
                eligible = [
                    item
                    for item in eligible_for_guardrail(guardrail)
                    if _evaluate_candidate(item, guardrail, recent_average_price_by_product)
                    is None
                ]
                lowest = min((item.total_amount for item in eligible), default=None)
                tied = [item for item in eligible if item.total_amount == lowest]
                if len(tied) > 1:
                    reason = "tied_responses"
                elif lowest is None:
                    reason = "no_eligible_response"
                elif candidate.total_amount != lowest:
                    reason = "not_lowest_price"
                else:
                    reason = "would_fire"
                    if guardrail.id in ambiguous_guardrail_ids:
                        reason = "ambiguous_guardrails"
        explanations.append(GuardrailExplanation(guardrail.id, False, reason))

    return explanations
