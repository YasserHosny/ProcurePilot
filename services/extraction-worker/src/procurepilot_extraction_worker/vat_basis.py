"""Conservative document-level VAT evidence, independent of extraction provider."""

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class VatBasis:
    prices_include_vat: bool
    rate: Decimal
    evidence: str
    confidence: float


_NORMALISE = str.maketrans("٠١٢٣٤٥٦٧٨٩٪", "0123456789%")
_STATEMENT = re.compile(
    r"(?<!\w)(?P<total>(?:الإجمالي|الاجمالي|المجموع|(?:grand\s+)?total)\s+)?"
    r"(?:(?:(?:الأسعار|الاسعار|السعر)\s+)?شامل[ةه]?\s+ضريب[ةه]"
    r"(?:\s+القيم[ةه]\s+المضاف[ةه])?|"
    r"prices?\s+(?:include|incl\.?)\s+VAT|inclusive\s+of\s+VAT|VAT\s+inclusive|incl\.?\s+VAT)"
    r"\s*\(?(?P<percent>\d+(?:[.,]\d+)?)\s*%\)?",
    re.IGNORECASE,
)


def detect_vat_basis(
    text: str, *, line_sum: Decimal | None, stated_total: Decimal | None
) -> VatBasis | None:
    normalised = text.translate(_NORMALISE)
    candidates: list[VatBasis] = []
    for match in _STATEMENT.finditer(normalised):
        rate = Decimal(match["percent"].replace(",", ".")) / 100
        if not 0 <= rate < 1:
            continue
        evidence = text[match.start() : match.end()]
        if match["total"] is None:
            return VatBasis(True, rate, evidence, 0.80)
        if line_sum is None or stated_total is None:
            continue
        if abs(line_sum - stated_total) <= Decimal("0.01"):
            candidates.append(VatBasis(True, rate, evidence, 0.80))
        elif abs(line_sum * (1 + rate) - stated_total) <= Decimal("0.01"):
            candidates.append(VatBasis(False, rate, evidence, 0.80))
    return candidates[0] if candidates else None
