from procurepilot_extraction_worker.models import ExtractedField, ExtractionResult
from procurepilot_extraction_worker.worker import (
    SupplierMatch,
    _review_reason,
    _with_normalised_dates,
)


def _result(issue_date: object) -> ExtractionResult:
    return ExtractionResult(
        method="bedrock",
        model_version="test",
        header={
            "currency": ExtractedField("currency", "EGP", 0.99),
            "issue_date": ExtractedField("issue_date", issue_date, 0.95),
        },
        lines=[],
    )


def test_normalises_date_to_iso_and_ambiguous_confidence_routes_low_confidence() -> None:
    normalized, parsed_dates, unparsed = _with_normalised_dates(_result("05/10/2026"), "EG")
    assert normalized.header["issue_date"].value == "05/10/2026"
    assert parsed_dates["issue_date"] == "2026-10-05"
    assert normalized.header["issue_date"].confidence == 0.5
    assert not unparsed
    assert (
        _review_reason(normalized, "not_applicable", 0.85, SupplierMatch(None, None, False))
        == "low_confidence"
    )


def test_unparsed_date_stays_as_evidence_and_routes_to_date_review() -> None:
    normalized, parsed_dates, unparsed = _with_normalised_dates(_result("soon"), "EG")
    assert normalized.header["issue_date"].value == "soon"
    assert parsed_dates["issue_date"] is None
    assert unparsed
    assert (
        _review_reason(
            normalized,
            "not_applicable",
            0.85,
            SupplierMatch(None, None, False),
            has_unparsed_date=unparsed,
        )
        == "date_unparsed"
    )
