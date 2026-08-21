from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from procurepilot_api.modules.matching.scoring import ScoreInputs, reason_payload, score_candidate


@dataclass(frozen=True)
class DeterministicCandidate:
    workspace_product_id: UUID
    confidence: Decimal
    reasons: dict[str, object]
    match_type: str


def find_deterministic_candidate(
    *,
    line: dict[str, object],
    products: list[dict[str, object]],
    aliases: list[dict[str, object]],
    supplier_code_aliases: list[dict[str, object]],
) -> DeterministicCandidate | None:
    gtin = _line_field(line, "gtin")
    if gtin:
        for product in products:
            if _normalise(product.get("gtin")) == _normalise(gtin):
                return _candidate(product, "gtin_match")

    supplier_code = _line_field(line, "supplier_product_code")
    if supplier_code:
        for alias in supplier_code_aliases:
            if _normalise(alias.get("alias_text")) == _normalise(supplier_code):
                return _candidate(alias, "supplier_code_match")

    original_text = str(line.get("original_text") or "")
    for alias in aliases:
        if _normalise(alias.get("alias_text")) == _normalise(original_text):
            return _candidate(alias, "alias_hit")
    return None


def _candidate(row: dict[str, object], match_type: str) -> DeterministicCandidate:
    inputs = ScoreInputs(
        deterministic_signal=Decimal("1"),
        lexical_similarity=Decimal("1"),
        semantic_similarity=Decimal("1"),
        brand_match=Decimal("1"),
        variant_match=Decimal("1"),
        pack_unit_match=Decimal("1"),
    )
    return DeterministicCandidate(
        workspace_product_id=UUID(
            str(row["workspace_product_id"] if "workspace_product_id" in row else row["id"])
        ),
        confidence=score_candidate(inputs),
        reasons=reason_payload(
            alias_hit=match_type == "alias_hit",
            gtin_match=match_type == "gtin_match",
            supplier_code_match=match_type == "supplier_code_match",
            inputs=inputs,
        ),
        match_type=match_type,
    )


def _line_field(line: dict[str, object], field_name: str) -> str | None:
    direct = line.get(field_name)
    if direct:
        return str(direct)
    extracted = line.get("extracted_fields")
    if isinstance(extracted, dict) and extracted.get(field_name):
        return str(extracted[field_name])
    return None


def _normalise(value: object) -> str:
    return str(value or "").strip().casefold()
