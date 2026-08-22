from __future__ import annotations

from decimal import Decimal

import pytest

from procurepilot_extraction_worker.models import ExtractedField, ExtractedLine, ExtractionResult
from procurepilot_extraction_worker.validation import parse_decimal, validate_arithmetic


def test_arithmetic_validation_reconciles_with_exact_decimal() -> None:
    result = ExtractionResult(
        method="structured_parse",
        model_version="test",
        header={"currency": ExtractedField("currency", "GBP", 1.0)},
        lines=[
            ExtractedLine(
                1,
                "row",
                {
                    "quantity": ExtractedField("quantity", "2", 1.0),
                    "unit_price": ExtractedField(
                        "unit_price",
                        {"amount": "10.00", "currency": "GBP"},
                        1.0,
                    ),
                },
            )
        ],
        stated_total=ExtractedField("stated_total", {"amount": "20.00", "currency": "GBP"}, 1.0),
    )

    validation = validate_arithmetic(result)

    assert validation.status == "reconciled"
    assert validation.computed_total == Decimal("20.00")


def test_arithmetic_validation_flags_mismatch_regardless_of_confidence() -> None:
    result = ExtractionResult(
        method="bedrock",
        model_version="stub",
        header={"currency": ExtractedField("currency", "GBP", 0.99)},
        lines=[
            ExtractedLine(
                1,
                "row",
                {
                    "quantity": ExtractedField("quantity", "2", 0.99),
                    "unit_price": ExtractedField(
                        "unit_price",
                        {"amount": "10.00", "currency": "GBP"},
                        0.99,
                    ),
                },
            )
        ],
        stated_total=ExtractedField("stated_total", {"amount": "25.00", "currency": "GBP"}, 0.99),
    )

    assert validate_arithmetic(result).status == "mismatch"


def test_validation_reuses_catalogue_decimal_parser_for_ambiguous_locale_values() -> None:
    with pytest.raises(ValueError, match="ambiguous decimal separator"):
        parse_decimal("1,234")
