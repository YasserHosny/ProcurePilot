from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from procurepilot_api.modules.offers.schemas import (
    Offer,
    Recommendation,
    RecommendationEvidence,
    RiskNote,
)

WEIGHTS = {
    "cost": Decimal("0.55"),
    "match_confidence": Decimal("0.20"),
    "reliability": Decimal("0.15"),
    "lead_time": Decimal("0.10"),
}
SUPPLIER_IQ_WEIGHTS = {
    "cost": Decimal("0.45"),
    "match_confidence": Decimal("0.17"),
    "reliability": Decimal("0.13"),
    "lead_time": Decimal("0.10"),
    "supplier_risk": Decimal("0.15"),
}
TIE_BREAK_RULE = [
    "lower_projected_total_amount",
    "higher_match_confidence",
    "higher_supplier_reliability_null_last",
    "lower_supplier_lead_time_null_last",
    "later_valid_to_null_open_ended_first",
    "lexicographic_supplier_name",
    "lexicographic_supplier_id",
]


@dataclass(frozen=True)
class ScoredOffer:
    offer: Offer
    score: Decimal
    components: dict[str, Decimal]


def recommend_offer(
    offers: list[Offer],
    *,
    now: datetime | None = None,
    supplier_risk_scores: dict[UUID, str | Decimal] | None = None,
) -> Recommendation | None:
    eligible = [offer for offer in offers if not offer.is_expired]
    if not eligible:
        return None
    evaluated_at = now or datetime.now(UTC)
    cheapest = min(_money_amount(offer) for offer in eligible)
    weights = SUPPLIER_IQ_WEIGHTS if supplier_risk_scores else WEIGHTS
    scored = [_score_offer(offer, cheapest, weights, supplier_risk_scores) for offer in eligible]
    scored.sort(key=_sort_key)
    winner = scored[0]
    second = scored[1] if len(scored) > 1 else None
    rounded_winner = _score_string(winner.score)
    margin = None if second is None else winner.score - second.score
    tie_applied = second is not None and _score_string(winner.score) == _score_string(second.score)
    return Recommendation(
        recommended_offer_id=winner.offer.id,
        score=rounded_winner,
        confidence=_confidence(winner.score, margin),
        valid_from=winner.offer.valid_from,
        valid_to=winner.offer.valid_to,
        risk_notes=_risk_notes(winner.offer, evaluated_at, supplier_risk_scores),
        evidence=RecommendationEvidence(
            weights={key: format(value, "f") for key, value in weights.items()},
            components={key: _score_string(value) for key, value in winner.components.items()},
            winning_margin=None if margin is None else _score_string(margin),
            tie_break={
                "applied": tie_applied,
                "rule": TIE_BREAK_RULE,
                "winner_supplier_id": str(winner.offer.supplier_id),
            },
        ),
    )


def _score_offer(
    offer: Offer,
    cheapest: Decimal,
    weights: dict[str, Decimal],
    supplier_risk_scores: dict[UUID, str | Decimal] | None = None,
) -> ScoredOffer:
    total = _money_amount(offer)
    components = {
        "cost": min(Decimal("1"), cheapest / total) if total > 0 else Decimal("0"),
        "match_confidence": Decimal(offer.match_confidence),
        "reliability": (
            Decimal(offer.reliability_score) if offer.reliability_score else Decimal("0.500")
        ),
        "lead_time": _lead_time_score(offer.lead_time_days),
    }
    scoring_components = dict(components)
    if "supplier_risk" in weights:
        raw_risk = supplier_risk_scores.get(offer.supplier_id) if supplier_risk_scores else None
        risk_dec = _clamp_score(
            Decimal(str(raw_risk)) if raw_risk is not None else Decimal("0.500")
        )
        components["supplier_risk"] = risk_dec
        scoring_components["supplier_risk"] = Decimal("1") - risk_dec

    score = sum(weights[key] * scoring_components[key] for key in weights)
    return ScoredOffer(offer=offer, score=score, components=components)


def _sort_key(scored: ScoredOffer) -> tuple[object, ...]:
    offer = scored.offer
    reliability = Decimal(offer.reliability_score) if offer.reliability_score else Decimal("-1")
    lead_time = offer.lead_time_days if offer.lead_time_days is not None else 10**9
    valid_to_rank = datetime.max.replace(tzinfo=UTC) if offer.valid_to is None else offer.valid_to
    return (
        -_score_rounded(scored.score),
        _money_amount(offer),
        -Decimal(offer.match_confidence),
        -reliability,
        lead_time,
        -valid_to_rank.timestamp(),
        offer.supplier_name,
        str(offer.supplier_id),
    )


def _lead_time_score(days: int | None) -> Decimal:
    if days is None:
        return Decimal("0.500")
    capped = min(days, 30)
    return Decimal("1") - (Decimal(capped) / Decimal("30"))


def _confidence(score: Decimal, margin: Decimal | None) -> str:
    if score >= Decimal("0.850") and (margin is None or margin >= Decimal("0.050")):
        return "high"
    if score >= Decimal("0.700") or score >= Decimal("0.850"):
        return "medium"
    return "low"


def _risk_notes(
    offer: Offer,
    now: datetime,
    supplier_risk_scores: dict[UUID, str | Decimal] | None = None,
) -> list[RiskNote]:
    risks: list[RiskNote] = []
    if offer.valid_to is not None and now <= offer.valid_to <= now + timedelta(days=7):
        risks.append("price_expiring_soon")
    if Decimal(offer.match_confidence) < Decimal("0.850"):
        risks.append("low_match_confidence")
    if offer.reliability_score is not None and Decimal(offer.reliability_score) < Decimal("0.600"):
        risks.append("low_supplier_reliability")
    if supplier_risk_scores:
        winner_risk = supplier_risk_scores.get(offer.supplier_id)
        if winner_risk is not None:
            w_risk = Decimal(str(winner_risk))
            if w_risk >= Decimal("0.70"):
                risks.append("high_supplier_risk")
            elif w_risk >= Decimal("0.30"):
                risks.append("elevated_supplier_risk")
    return risks


def _money_amount(offer: Offer) -> Decimal:
    return Decimal(offer.landed_cost.amount)


def _score_rounded(score: Decimal) -> Decimal:
    return score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _score_string(score: Decimal) -> str:
    return format(_score_rounded(score), "f")


def _clamp_score(score: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), score))


def offer_id_from_recommendation(recommendation: Recommendation | None) -> UUID | None:
    return None if recommendation is None else recommendation.recommended_offer_id
