from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

STUB_EMBEDDING_MODEL = "stub-hash-v1"
SCORING_VERSION = "matching-score-v2"
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
WEIGHTS_STUB_EMBEDDING: dict[str, Decimal] = {
    **WEIGHTS,
    "lexical": WEIGHTS["lexical"] + WEIGHTS["semantic"],
    "semantic": Decimal("0.00"),
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


def active_weights(embedding_model: str) -> dict[str, Decimal]:
    if embedding_model == STUB_EMBEDDING_MODEL:
        return WEIGHTS_STUB_EMBEDDING
    return WEIGHTS


def score_candidate(
    inputs: ScoreInputs, *, embedding_model: str = STUB_EMBEDDING_MODEL
) -> Decimal:
    weights = active_weights(embedding_model)
    raw = (
        weights["deterministic"] * _clamp(inputs.deterministic_signal)
        + weights["lexical"] * _clamp(inputs.lexical_similarity)
        + weights["semantic"] * _clamp(inputs.semantic_similarity)
        + weights["brand"] * _optional(inputs.brand_match)
        + weights["variant"] * _optional(inputs.variant_match)
        + weights["pack_unit"] * _optional(inputs.pack_unit_match)
        + weights["pack_size"] * _optional(inputs.pack_size_plausibility)
        + weights["price"] * _optional(inputs.price_plausibility)
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
