from __future__ import annotations

from typing import Protocol

from procurepilot_extraction_worker.models import ExtractionResult


class ExtractionProviderError(RuntimeError):
    fallback_allowed = True


class ExtractionProvider(Protocol):
    method: str
    model_version: str

    def extract(
        self,
        *,
        document_id: str,
        mime_type: str,
        storage_path: str,
    ) -> ExtractionResult: ...
