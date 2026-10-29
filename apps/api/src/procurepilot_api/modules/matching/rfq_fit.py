"""Pure, replayable RFQ fit rule (spec 023, research R3 calibration)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from procurepilot_api.modules.catalogue.units import canonical_base_unit
from procurepilot_api.modules.rfq.read_api import RfqContext, RfqLineContext

RULE_VERSION = "rfq-fit-v1"
_QUANT = Decimal("0.0001")
type PackCheck = Literal["equal", "conflict", "unknown"]
# Copied from extraction-worker azure_di._normalise_header; no cross-service import.
_FOLD = str.maketrans("أإآٱىئة", "ااااييه")
_MARKS = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u0640\u06d6-\u06ed\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_UNITS = {
    "kilogram": ("mass", Decimal("1000")),
    "gram": ("mass", Decimal("1")),
    "litre": ("volume", Decimal("1000")),
    "millilitre": ("volume", Decimal("1")),
    "each": ("count", Decimal("1")),
}


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return " ".join(_MARKS.sub("", text).translate(_FOLD).translate(_DIGITS).casefold().split())


def _stem(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    # Remove innermost segments first, including mixed/nested brackets.
    while True:
        stripped = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", name)
        if stripped == name:
            return normalise_text(name)
        name = stripped


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def _trigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for word in _tokens(text):
        padded = "  " + word + " "
        grams.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return grams


def trigram_similarity(left: str, right: str) -> Decimal:
    a, b = _trigrams(left), _trigrams(right)
    return (Decimal(len(a & b)) / Decimal(len(a | b)) if a or b else Decimal("0")).quantize(_QUANT)


@dataclass(frozen=True)
class RfqLineScore:
    rfq_line: RfqLineContext
    wording_score: Decimal
    score: Decimal
    pack_check: PackCheck
    reasons: dict[str, object]


@dataclass(frozen=True)
class RfqFit:
    matched_rfq_line: RfqLineContext | None
    fitting_lines: tuple[RfqLineContext, ...]
    scores: tuple[RfqLineScore, ...]
    pack_check: PackCheck
    reasons: dict[str, object]


def _pack_check(
    pack_count: Decimal | None,
    unit_size: Decimal | None,
    pack_unit: str | None,
    line: RfqLineContext,
) -> tuple[PackCheck, Decimal | None, str | None]:
    if (
        pack_count is None
        or unit_size is None
        or pack_unit is None
        or line.pack_base_quantity is None
        or line.base_unit is None
    ):
        return "unknown", None, None
    quantity = pack_count * unit_size
    quoted_unit = canonical_base_unit(pack_unit)
    base_unit = canonical_base_unit(line.base_unit)
    if quoted_unit != base_unit:
        source, target = _UNITS.get(quoted_unit), _UNITS.get(base_unit)
        if source is None or target is None or source[0] != target[0]:
            return "conflict", quantity, quoted_unit
        quantity = quantity * source[1] / target[1]
    tolerance = abs(line.pack_base_quantity) * Decimal("0.005")
    return (
        "equal" if abs(quantity - line.pack_base_quantity) <= tolerance else "conflict",
        quantity,
        base_unit,
    )


def fit_against_rfq(
    *,
    original_text: str,
    pack_count: Decimal | None,
    unit_size: Decimal | None,
    pack_unit: str | None,
    rank: int,
    context: RfqContext,
    floor: Decimal,
    margin: Decimal,
    excluded_products: frozenset[UUID] = frozenset(),
) -> RfqFit:
    """Ranks are 1-based order, independent of stored line numbers/positions.

    Scores are bounded to one, and the floor always uses wording before the position bonus.
    Even a wide winning margin cannot resolve two fitting RFQ lines.
    """
    text = normalise_text(original_text)
    tokens = _tokens(text)
    scores: list[RfqLineScore] = []
    ordered = sorted(context.lines, key=lambda line: line.position)
    for position, line in enumerate(ordered, start=1):
        if line.workspace_product_id in excluded_products:
            continue
        stem = _stem(line.product_name)
        stem_tokens = _tokens(stem)
        containment = bool(tokens and stem_tokens) and (
            tokens <= stem_tokens or stem_tokens <= tokens
        )
        wording = max(
            trigram_similarity(text, stem),
            *(trigram_similarity(text, normalise_text(alias)) for alias in line.aliases),
            Decimal("1") if containment else Decimal("0"),
        ).quantize(_QUANT)
        pack, quantity, quantity_unit = _pack_check(pack_count, unit_size, pack_unit, line)
        bonus = Decimal(".05") if wording >= floor and position == rank else Decimal("0")
        score = min(Decimal("1"), wording + bonus).quantize(_QUANT)
        rfq: dict[str, object] = {
            "rule_version": RULE_VERSION,
            "rfq_id": str(context.rfq_id),
            "rfq_line_id": str(line.rfq_line_id),
            "position": position,
            "wording_score": format(wording, "f"),
            "pack_check": pack,
        }
        measured = {"lexical_similarity": format(wording, "f")}
        if quantity is not None and line.pack_base_quantity is not None:
            rfq["quoted_pack_base_quantity"] = format(quantity, ".6f")
            rfq["rfq_pack_base_quantity"] = format(line.pack_base_quantity, ".6f")
            rfq["quoted_pack_unit"] = quantity_unit
            rfq["rfq_pack_unit"] = canonical_base_unit(line.base_unit)
            measured["pack_unit_match"] = "1.0000" if pack == "equal" else "0.0000"
        scores.append(
            RfqLineScore(
                line,
                wording,
                score,
                pack,
                {
                    "rfq": rfq,
                    "measured": measured,
                    "alias_hit": False,
                    "gtin_match": False,
                    "supplier_code_match": False,
                },
            )
        )
    # Stable RFQ order breaks equal scores, preserving repeatability.
    scores.sort(key=lambda item: item.score, reverse=True)
    fitting = tuple(
        s.rfq_line for s in scores if s.wording_score >= floor and s.pack_check != "conflict"
    )
    for item in scores:
        item.reasons["rfq"]["fitting_rfq_line_ids"] = [str(line.rfq_line_id) for line in fitting]
    matched = None
    selected = next((s for s in scores if fitting and s.rfq_line == fitting[0]), None)
    if len(fitting) == 1 and selected is not None:
        other = max((s.score for s in scores if s is not selected), default=Decimal("0"))
        required = margin * (2 if selected.pack_check == "unknown" else 1)
        if selected.score - other >= required:
            matched = selected.rfq_line
    top = selected or (scores[0] if scores else None)
    return RfqFit(
        matched,
        fitting,
        tuple(scores),
        top.pack_check if top else "unknown",
        top.reasons
        if top
        else {"rfq": {"rfq_id": str(context.rfq_id), "rule_version": RULE_VERSION}, "measured": {}},
    )
