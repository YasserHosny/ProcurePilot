from __future__ import annotations

from procurepilot_extraction_worker.models import ExtractionResult
from procurepilot_extraction_worker.providers import ExtractionProviderError, FakeExtractionProvider


class BedrockExtractionProvider:
    """Bedrock-shaped provider; real network call is intentionally pending credentials."""

    method = "bedrock"
    model_version = "anthropic.claude-3-haiku-20240307-v1:0"

    def extract(self, *, document_id: str, mime_type: str, storage_path: str) -> ExtractionResult:
        if not document_id or not storage_path:
            raise ExtractionProviderError("invalid bedrock request shape")
        # Until credentials arrive, use the deterministic stub behind the same schema boundary.
        return FakeExtractionProvider().extract(
            document_id=document_id, mime_type=mime_type, storage_path=storage_path
        )
