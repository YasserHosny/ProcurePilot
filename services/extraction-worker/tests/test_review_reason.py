from __future__ import annotations

from procurepilot_extraction_worker.models import ExtractedField, ExtractedLine, ExtractionResult
from procurepilot_extraction_worker.structured_parse import parse_structured_content
from procurepilot_extraction_worker.worker import (
    SupplierMatch,
    _money_amount,
    _review_reason,
    _with_currency_suggestion,
)

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


def test_low_confidence_currency_uses_low_confidence_review_reason() -> None:
    result = ExtractionResult(
        method="structured_parse",
        model_version="test",
        header={"currency": ExtractedField("currency", "EGP", 0.5)},
        lines=[],
    )

    assert _review_reason(result, "not_applicable", 0.85, _NO_MATCH) == "low_confidence"


def test_unresolved_currency_is_routed_to_review_without_a_guess() -> None:
    result = parse_structured_content(
        b"description,quantity,unit_price\nTomatoes,1,10.00\n", mime_type="text/csv"
    )

    assert "currency" not in result.header
    assert result.lines[0].fields["unit_price"].value == {"amount": "10.00", "currency": None}
    assert _review_reason(result, "not_applicable", 0.75, _NO_MATCH) == "currency_unresolved"
    suggested = _with_currency_suggestion(result, "EGP")
    assert suggested.suggested_currency == "EGP"
    assert "currency" not in suggested.header


def test_resolved_currency_gets_no_suggestion() -> None:
    result = ExtractionResult(
        method="structured_parse",
        model_version="test",
        header={"currency": ExtractedField("currency", "EGP", 1.0)},
        lines=[],
    )

    assert _with_currency_suggestion(result, "USD").suggested_currency is None


def test_uncurried_money_is_routed_to_review_and_not_persisted_as_amount() -> None:
    line = ExtractedLine(
        line_number=1,
        original_text="Tomatoes 10.00",
        fields={
            "unit_price": ExtractedField(
                "unit_price", {"amount": "10.00", "currency": None}, 1.0
            )
        },
    )
    result = ExtractionResult(
        method="structured_parse",
        model_version="test",
        header={},
        lines=[line],
    )

    assert _money_amount(line, "unit_price") is None
    assert _review_reason(result, "not_applicable", 0.85, _NO_MATCH) == "currency_unresolved"
