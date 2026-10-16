from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ExtractionMethod = Literal["structured_parse", "bedrock", "azure_di"]


@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: Any
    confidence: float
    source_page: int | None = None
    source_region: dict[str, Any] | None = None
    typed_value: object | None = None


@dataclass(frozen=True)
class ExtractedLine:
    line_number: int
    original_text: str
    fields: dict[str, ExtractedField]


@dataclass(frozen=True)
class ExtractionResult:
    method: ExtractionMethod
    model_version: str
    header: dict[str, ExtractedField]
    lines: list[ExtractedLine]
    stated_total: ExtractedField | None = None
    cost_usd: float = 0.0
    # Never stored as the quotation's currency: tenant home currency offered to the reviewer
    # only when the document itself did not evidence one (spec 022 FR-011).
    suggested_currency: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
