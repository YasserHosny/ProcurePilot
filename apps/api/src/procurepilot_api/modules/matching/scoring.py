from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

SCORING_VERSION = "matching-score-v1"
NEUTRAL_SCORE = Decimal("0.5")
WEIGHTS: dict[str, Decimal] = {
    "deterministic": Decimal("0.30"),
    "lexical": Decimal("0.20"),
    "semantic": Decimal("0.20"),
    "brand": Decimal("0.10"),
    "variant": Decimal("0.07"),
    "pack_unit": Decimal("0.06"),
    "pack_size": Decimal("0.04"),
    "price": Decimal("0.03"),
}
CONFIDENCE_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class ScoreInputs:
    deterministic_signal: Decimal = Decimal("0")
    lexical_similarity: Decimal = Decimal("0")
    semantic_similarity: Decimal = Decimal("0")
    brand_match: Decimal | None = None
    variant_match: Decimal | None = None
    pack_unit_match: Decimal | None = None
    pack_size_plausibility: Decimal | None = None
    price_plausibility: Decimal | None = None


def score_candidate(inputs: ScoreInputs) -> Decimal:
    raw = (
        WEIGHTS["deterministic"] * _clamp(inputs.deterministic_signal)
        + WEIGHTS["lexical"] * _clamp(inputs.lexical_similarity)
        + WEIGHTS["semantic"] * _clamp(inputs.semantic_similarity)
        + WEIGHTS["brand"] * _optional(inputs.brand_match)
        + WEIGHTS["variant"] * _optional(inputs.variant_match)
        + WEIGHTS["pack_unit"] * _optional(inputs.pack_unit_match)
        + WEIGHTS["pack_size"] * _optional(inputs.pack_size_plausibility)
        + WEIGHTS["price"] * _optional(inputs.price_plausibility)
    )
    return _clamp(raw).quantize(CONFIDENCE_QUANT, rounding=ROUND_HALF_UP)


def reason_payload(
    *,
    alias_hit: bool = False,
    gtin_match: bool = False,
    supplier_code_match: bool = False,
    inputs: ScoreInputs,
) -> dict[str, object]:
    return {
        "alias_hit": alias_hit,
        "gtin_match": gtin_match,
        "supplier_code_match": supplier_code_match,
        "lexical_similarity": decimal_string(inputs.lexical_similarity),
        "semantic_similarity": decimal_string(inputs.semantic_similarity),
        "feature_score": {
            "brand_match": decimal_string(_optional(inputs.brand_match)),
            "variant_match": decimal_string(_optional(inputs.variant_match)),
            "pack_unit_match": decimal_string(_optional(inputs.pack_unit_match)),
            "pack_size_plausibility": decimal_string(_optional(inputs.pack_size_plausibility)),
            "price_plausibility": decimal_string(_optional(inputs.price_plausibility)),
        },
    }


def decimal_string(value: Decimal | object) -> str:
    return format(Decimal(str(value)).quantize(CONFIDENCE_QUANT, rounding=ROUND_HALF_UP), "f")


def _optional(value: Decimal | None) -> Decimal:
    return NEUTRAL_SCORE if value is None else _clamp(value)


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), Decimal(str(value))))
