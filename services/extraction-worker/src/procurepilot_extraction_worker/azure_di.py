from __future__ import annotations

from procurepilot_extraction_worker.models import ExtractionResult
from procurepilot_extraction_worker.providers import ExtractionProviderError, FakeExtractionProvider


class AzureDocumentIntelligenceProvider:
    """Azure Document Intelligence-shaped fallback; real network call pending credentials."""

    method = "azure_di"
    model_version = "prebuilt-layout:2024-11-30"

    def extract(self, *, document_id: str, mime_type: str, storage_path: str) -> ExtractionResult:
        if not document_id or not storage_path:
            raise ExtractionProviderError("invalid azure document intelligence request shape")
        result = FakeExtractionProvider().extract(
            document_id=document_id, mime_type=mime_type, storage_path=storage_path
        )
        return ExtractionResult(
            method="azure_di",
            model_version=self.model_version,
            header=result.header,
            lines=result.lines,
            stated_total=result.stated_total,
            cost_usd=result.cost_usd,
            warnings=result.warnings,
        )
