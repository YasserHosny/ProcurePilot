from datetime import date
from types import SimpleNamespace as NS

from procurepilot_extraction_worker.azure_di import _clean_number, _parse_invoice_result
from procurepilot_extraction_worker.worker import _with_normalised_dates


def test_arabic_decimal_is_preserved_in_total_quantity_and_unit_price() -> None:
    fields = {
        "InvoiceTotal": NS(content="١٢٥٠٫٥٠", confidence=0.9),
        "Items": NS(
            value_array=[
                NS(
                    value_object={
                        "Quantity": NS(content="١٢٥٠٫٥٠", confidence=0.9),
                        "UnitPrice": NS(content="١٢٥٠٫٥٠", confidence=0.9),
                    }
                )
            ]
        ),
    }
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert result.stated_total.value["amount"] == "1250.50"
    assert result.lines[0].fields["quantity"].value == "1250.50"
    assert result.lines[0].fields["unit_price"].value["amount"] == "1250.50"
    assert _clean_number("1,234") is None


def test_conflicting_currency_markers_store_no_currency() -> None:
    fields = {
        "InvoiceTotal": NS(content="$10", confidence=0.9),
        "AmountDue": NS(content="ج.م 10", confidence=0.9),
    }
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert "currency" not in result.header
    assert result.stated_total.value["currency"] is None


def test_invoice_dates_preserve_azure_content_as_evidence() -> None:
    fields = {
        "InvoiceDate": NS(value_date=date(2026, 10, 16), content="16/10/2026", confidence=0.9),
        "DueDate": NS(value_date=None, content="20/10/2026", confidence=0.8),
    }
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    assert result.header["issue_date"].value == "16/10/2026"
    assert result.header["expiry_date"].value == "20/10/2026"


def test_azure_value_date_wins_for_parsed_date_but_content_remains_evidence() -> None:
    fields = {
        "InvoiceDate": NS(value_date=date(2026, 5, 10), content="05/10/2026", confidence=0.9),
    }
    result = _parse_invoice_result(NS(documents=[NS(fields=fields)]), "test")
    normalized, parsed_dates, _ = _with_normalised_dates(result, "EG")
    assert normalized.header["issue_date"].value == "05/10/2026"
    assert parsed_dates["issue_date"] == "2026-05-10"
    assert normalized.header["issue_date"].confidence == 0.9
