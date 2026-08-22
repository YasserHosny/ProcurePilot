from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True)
class ProvenanceField:
    quotation_id: UUID
    entity_type: Literal["quotation", "quotation_line"]
    entity_id: UUID
    field_name: str
    extracted_value: Any
    confidence: str
    extraction_method: Literal["structured_parse", "bedrock", "azure_di"]
    model_version: str
    source_page: int | None = None
    source_region: dict[str, Any] | None = None


def field_extraction_row(tenant_id: UUID, field: ProvenanceField) -> dict[str, object]:
    return {
        "tenant_id": str(tenant_id),
        "quotation_id": str(field.quotation_id),
        "entity_type": field.entity_type,
        "entity_id": str(field.entity_id),
        "field_name": field.field_name,
        "extracted_value": field.extracted_value,
        "confidence": field.confidence,
        "source_page": field.source_page,
        "source_region": field.source_region,
        "extraction_method": field.extraction_method,
        "model_version": field.model_version,
    }
