from __future__ import annotations

import hashlib
from typing import Protocol

from procurepilot_extraction_worker.models import (
    ExtractedField,
    ExtractedLine,
    ExtractionResult,
)


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


class FakeExtractionProvider:
    """Deterministic offline provider for the CI e2e stack (EXTRACTION_PROVIDER_MODE=stub).

    Explicitly selected, never a fallback: production keeps the loud bedrock -> azure_di
    failure path. The e2e specs' whole quotation recipe (support/canonical-flow.ts) encodes
    this provider's fixed output — two lines totalling £75.00, a hash-chosen mismatched
    stated total, and a low-confidence issue date — so its values must not drift.
    """

    method = "bedrock"
    model_version = "stub-provider-v1"

    def extract(self, *, document_id: str, mime_type: str, storage_path: str) -> ExtractionResult:
        seed = int(hashlib.sha256(f"{document_id}:{storage_path}".encode()).hexdigest()[:8], 16)
        low_confidence = 0.62 if seed % 2 == 0 else 0.78
        mismatch_total = "88.00" if seed % 3 == 0 else "77.00"
        return ExtractionResult(
            method="bedrock",
            model_version=self.model_version,
            header={
                "supplier_name": ExtractedField(
                    "supplier_name",
                    f"Stub Supplier {seed % 17}",
                    0.94,
                    1,
                    {"bbox": [0.1, 0.1, 0.4, 0.15]},
                ),
                "currency": ExtractedField(
                    "currency",
                    "GBP",
                    0.97,
                    1,
                    {"bbox": [0.72, 0.1, 0.8, 0.15]},
                ),
                "issue_date": ExtractedField("issue_date", "2026-08-21", low_confidence, 1, None),
                "expiry_date": ExtractedField("expiry_date", "2026-09-20", 0.9, 1, None),
            },
            lines=[
                ExtractedLine(
                    1,
                    "Tomatoes case 10 kg x 3 @ 12.00",
                    {
                        "quantity": ExtractedField("quantity", "3", 0.96, 1, None),
                        "pack_count": ExtractedField("pack_count", 1, 0.91, 1, None),
                        "unit_size": ExtractedField("unit_size", "10", 0.9, 1, None),
                        "pack_unit": ExtractedField("pack_unit", "kilogram", 0.88, 1, None),
                        "unit_price": ExtractedField(
                            "unit_price",
                            {"amount": "12.00", "currency": "GBP"},
                            0.93,
                            1,
                            None,
                        ),
                    },
                ),
                ExtractedLine(
                    2,
                    "Olive oil tin 5 litre x 2 @ 20.00 less 1.00",
                    {
                        "quantity": ExtractedField("quantity", "2", 0.95, 1, None),
                        "pack_count": ExtractedField("pack_count", 1, 0.89, 1, None),
                        "unit_size": ExtractedField("unit_size", "5", 0.89, 1, None),
                        "pack_unit": ExtractedField("pack_unit", "litre", 0.9, 1, None),
                        "unit_price": ExtractedField(
                            "unit_price",
                            {"amount": "20.00", "currency": "GBP"},
                            0.92,
                            1,
                            None,
                        ),
                        "discount": ExtractedField(
                            "discount",
                            {"amount": "1.00", "currency": "GBP"},
                            0.86,
                            1,
                            None,
                        ),
                    },
                ),
            ],
            stated_total=ExtractedField(
                "stated_total", {"amount": mismatch_total, "currency": "GBP"}, 0.9, 1, None
            ),
            cost_usd=0.0,
            warnings=("stub provider (real Bedrock/Azure DI wiring pending credentials)",),
        )
