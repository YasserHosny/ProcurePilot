from __future__ import annotations

from procurepilot_extraction_worker.models import ExtractedField, ExtractionResult
from procurepilot_extraction_worker.worker import SupplierMatch, _review_reason

_NO_MATCH = SupplierMatch(supplier_id=None, confidence=None, had_candidates=False)


def _empty_result() -> ExtractionResult:
    return ExtractionResult(
        method="azure_di",
        model_version="prebuilt-invoice:test",
        header={},
        lines=[],
        stated_total=None,
    )


def test_review_reason_flags_read_failure_when_nothing_extracted() -> None:
    # A provider can report "succeeded" while genuinely extracting zero lines and zero header
    # fields -- e.g. a real document Azure DI's prebuilt-invoice model doesn't recognise as an
    # invoice, with no table structure for its fallback either. Found live: a real PDF quote
    # extracted to zero lines/currency/total, silently reaching "extracted" status with no
    # review task raised, before this check existed.
    assert _review_reason(_empty_result(), "not_applicable", 0.75, _NO_MATCH) == "read_failure"


def test_review_reason_not_triggered_when_header_has_data_but_no_lines() -> None:
    # A document with header-level data (e.g. a stated total) but genuinely zero line items is
    # a different, already-covered case (falls through to no flag here, same as before this
    # fix) -- this test pins that the new check is specifically "extracted literally nothing",
    # not "extracted no lines".
    result = ExtractionResult(
        method="azure_di",
        model_version="prebuilt-invoice:test",
        header={"currency": ExtractedField("currency", "GBP", 0.9)},
        lines=[],
        stated_total=None,
    )
    assert _review_reason(result, "not_applicable", 0.75, _NO_MATCH) is None
