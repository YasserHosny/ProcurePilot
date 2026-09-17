from __future__ import annotations

import io
from decimal import Decimal

import openpyxl
import pytest

from procurepilot_api.modules.ingestion.catalogue_parser import (
    CatalogueParseError,
    parse_catalogue_file,
)


def _csv_bytes(rows: list[str]) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_parses_a_well_formed_csv_with_canonical_headers() -> None:
    content = _csv_bytes(
        [
            "product_name,unit_price,currency,unit,qty",
            "Whole Milk 2L,1.50,USD,bottle,12",
            "Sourdough Loaf,3.25,USD,loaf,6",
        ]
    )
    result = parse_catalogue_file(content, file_format="csv")

    assert len(result.valid_rows) == 2
    assert result.error_rows == []
    first = result.valid_rows[0]
    assert first.product_name == "Whole Milk 2L"
    assert first.unit_price_amount == Decimal("1.50")
    assert first.unit_price_currency == "USD"
    assert first.unit == "bottle"
    assert first.minimum_order_quantity == Decimal("12")


def test_resolves_alias_headers() -> None:
    content = _csv_bytes(
        [
            "item,price,curr",
            "Widget,9.99,GBP",
        ]
    )
    result = parse_catalogue_file(content, file_format="csv")

    assert result.column_mapping["product_name"] == "item"
    assert result.column_mapping["unit_price"] == "price"
    assert result.column_mapping["currency"] == "curr"
    assert len(result.valid_rows) == 1


def test_missing_required_column_rejects_the_whole_file() -> None:
    content = _csv_bytes(["name,curr", "Widget,GBP"])  # no price column at all

    with pytest.raises(CatalogueParseError) as excinfo:
        parse_catalogue_file(content, file_format="csv")

    assert "unit_price" in str(excinfo.value)


def test_missing_currency_column_rejects_the_whole_file() -> None:
    # Constitution non-negotiable #6: no bare numbers for money, ever — a file with no currency
    # column at all cannot be silently defaulted.
    content = _csv_bytes(["product_name,unit_price", "Widget,9.99"])

    with pytest.raises(CatalogueParseError):
        parse_catalogue_file(content, file_format="csv")


def test_row_level_errors_do_not_reject_the_whole_file() -> None:
    content = _csv_bytes(
        [
            "product_name,unit_price,currency",
            "Good Widget,9.99,GBP",
            ",5.00,GBP",  # missing product name
            "Bad Price Widget,not-a-number,GBP",
            "Bad Currency Widget,5.00,dollars",
            "Zero Price Widget,0,GBP",
        ]
    )
    result = parse_catalogue_file(content, file_format="csv")

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].product_name == "Good Widget"
    assert len(result.error_rows) == 4
    errors_by_reason = {e.error for e in result.error_rows}
    assert "missing_product_name" in errors_by_reason
    assert "unparseable_unit_price" in errors_by_reason
    assert "invalid_currency_code" in errors_by_reason
    assert "unit_price_not_positive" in errors_by_reason


def test_row_numbers_count_the_header_as_row_one() -> None:
    content = _csv_bytes(
        [
            "product_name,unit_price,currency",
            "First,1.00,USD",
            "Second,2.00,USD",
        ]
    )
    result = parse_catalogue_file(content, file_format="csv")

    assert [r.row_number for r in result.valid_rows] == [2, 3]


def test_parses_xlsx_with_numeric_cells() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["product_name", "unit_price", "currency"])
    sheet.append(["Widget", 4.5, "EUR"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = parse_catalogue_file(buffer.getvalue(), file_format="xlsx")

    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].unit_price_amount == Decimal("4.5")
    assert result.valid_rows[0].unit_price_currency == "EUR"


def test_empty_file_raises_parse_error() -> None:
    with pytest.raises(CatalogueParseError):
        parse_catalogue_file(b"", file_format="csv")


def test_non_utf8_csv_raises_catalogue_parse_error() -> None:
    # 0xe9 is 'é' in Latin-1, invalid standalone in UTF-8
    content = b"product_name,unit_price,currency\nCaf\xe9,1.00,USD\n"
    with pytest.raises(CatalogueParseError) as excinfo:
        parse_catalogue_file(content, file_format="csv")
    assert "file could not be decoded as UTF-8 text" in str(excinfo.value)


def test_corrupted_xlsx_raises_catalogue_parse_error() -> None:
    content = b"not a valid zip or xlsx file content"
    with pytest.raises(CatalogueParseError) as excinfo:
        parse_catalogue_file(content, file_format="xlsx")
    assert "file is not a valid XLSX workbook" in str(excinfo.value)


def test_header_only_csv_parses_with_zero_data_rows() -> None:
    content = _csv_bytes(["product_name,unit_price,currency"])
    result = parse_catalogue_file(content, file_format="csv")

    assert result.total_rows == 0
    assert result.valid_rows == []
    assert result.error_rows == []
    assert result.column_mapping["product_name"] == "product_name"
    assert result.column_mapping["unit_price"] == "unit_price"
    assert result.column_mapping["currency"] == "currency"


def test_header_only_xlsx_parses_with_zero_data_rows() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["product_name", "unit_price", "currency"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = parse_catalogue_file(buffer.getvalue(), file_format="xlsx")

    assert result.total_rows == 0
    assert result.valid_rows == []
    assert result.error_rows == []
    assert result.column_mapping["product_name"] == "product_name"
    assert result.column_mapping["unit_price"] == "unit_price"
    assert result.column_mapping["currency"] == "currency"

