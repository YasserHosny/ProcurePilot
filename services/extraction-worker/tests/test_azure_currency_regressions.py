from types import SimpleNamespace as NS

from procurepilot_extraction_worker.azure_di import _clean_number, _parse_invoice_result


def test_arabic_decimal_is_preserved_in_total_quantity_and_unit_price() -> None:
    fields = {
        "InvoiceTotal": NS(content="١٢٥٠٫٥٠", confidence=0.9),
        "Items": NS(value_array=[NS(value_object={
            "Quantity": NS(content="١٢٥٠٫٥٠", confidence=0.9),
            "UnitPrice": NS(content="١٢٥٠٫٥٠", confidence=0.9),
        })]),
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

