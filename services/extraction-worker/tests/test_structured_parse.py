from __future__ import annotations

from procurepilot_extraction_worker.structured_parse import parse_structured_content


def test_csv_structured_input_bypasses_llm_with_full_confidence() -> None:
    content = (
        b"supplier_name,currency,description,quantity,unit_price,stated_total\n"
        b"Acme,GBP,Tomatoes,2,10.00,20.00\n"
    )

    result = parse_structured_content(content, mime_type="text/csv")

    assert result.method == "structured_parse"
    assert result.model_version == "structured-quotation-parser-v1"
    assert result.header["currency"].confidence == 1.0
    assert result.lines[0].fields["quantity"].confidence == 1.0
    assert result.lines[0].fields["unit_price"].value == {"amount": "10.00", "currency": "GBP"}


def test_csv_structured_parser_rejects_ambiguous_decimal() -> None:
    content = b'currency,description,quantity,unit_price\nGBP,Tomatoes,1,"1,234"\n'

    try:
        parse_structured_content(content, mime_type="text/csv")
    except ValueError as exc:
        assert "ambiguous decimal separator" in str(exc)
    else:
        raise AssertionError("ambiguous decimal should be refused into review")
