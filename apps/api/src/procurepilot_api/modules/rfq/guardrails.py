from dataclasses import dataclass
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
