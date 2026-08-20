from __future__ import annotations

from pathlib import Path

import pytest

from procurepilot_api.modules.catalogue.csv_import import (
    ImportValidationReport,
    ProductImportRow,
    SupplierImportRow,
    commit_import,
    validate_import_file,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_product_happy_path_from_fixture() -> None:
    report = validate_import_file(
        kind="products",
        filename="products_valid.csv",
        content=(FIXTURES / "products_valid.csv").read_bytes(),
        content_type="text/csv",
    )

    assert report.valid
    assert report.row_count == 3
    assert len(report.preview) == 3
    assert report.errors == ()


def test_malformed_rows_report_file_line_numbers() -> None:
    report = validate_import_file(
        kind="products",
        filename="products_invalid.csv",
        content=(FIXTURES / "products_invalid.csv").read_bytes(),
        content_type="text/csv",
    )

    assert not report.valid
    assert any(
        error.line == 3
        and error.column == "pack_count"
        and error.reason == "value must be greater than zero"
        for error in report.errors
    )
    assert any(
        error.line == 4
        and error.column == "unit_size"
        and "ambiguous decimal separator" in error.reason
        for error in report.errors
    )


def test_missing_columns_are_reported_separately() -> None:
    report = validate_import_file(
        kind="products",
        filename="missing.csv",
        content=b"tenant_name,base_unit,unit_size\nOlive oil,litre,1.5\n",
        content_type="text/csv",
    )

    assert not report.valid
    assert report.missing_columns == ("pack_count",)
    assert report.errors == ()


def test_unrecognised_columns_are_reported_separately() -> None:
    report = validate_import_file(
        kind="products",
        filename="extra.csv",
        content=b"tenant_name,base_unit,pack_count,unit_size,unexpected\nOil,litre,6,1.5,x\n",
        content_type="text/csv",
    )

    assert not report.valid
    assert report.unrecognised_columns == ("unexpected",)
    assert report.errors == ()


def test_empty_file_is_reported() -> None:
    report = validate_import_file(
        kind="products",
        filename="empty.csv",
        content=b"",
        content_type="text/csv",
    )

    assert not report.valid
    assert report.file_error == "empty file"


def test_header_only_file_is_reported() -> None:
    report = validate_import_file(
        kind="products",
        filename="header.csv",
        content=b"tenant_name,base_unit,pack_count,unit_size\n",
        content_type="text/csv",
    )

    assert not report.valid
    assert report.file_error == "header-only file"


def test_non_csv_binary_is_refused_before_parsing() -> None:
    report = validate_import_file(
        kind="products",
        filename="catalogue.pdf",
        content=b"%PDF-1.7\x00binary",
        content_type="application/pdf",
    )

    assert not report.valid
    assert report.file_error == "not an accepted CSV file type"
    assert report.row_count == 0


def test_quoted_field_containing_comma() -> None:
    report = validate_import_file(
        kind="products",
        filename="quoted.csv",
        content=b'tenant_name,base_unit,pack_count,unit_size\n"Tomatoes, chopped",each,24,1\n',
        content_type="text/csv",
    )

    assert report.valid
    assert isinstance(report.rows[0], ProductImportRow)
    assert report.rows[0].tenant_name == "Tomatoes, chopped"


def test_field_containing_embedded_newline_keeps_start_line_number() -> None:
    content = (
        b"tenant_name,base_unit,pack_count,unit_size\n"
        b'"Multi\nline name",each,12,1\n'
        b"Bad decimal,litre,6,\"1,234\"\n"
    )

    report = validate_import_file(
        kind="products",
        filename="newlines.csv",
        content=content,
        content_type="text/csv",
    )

    assert not report.valid
    assert isinstance(report.rows[0], ProductImportRow)
    assert report.rows[0].line == 2
    assert report.errors[0].line == 4


def test_supplier_money_requires_currency() -> None:
    report = validate_import_file(
        kind="suppliers",
        filename="suppliers.csv",
        content=b"name,minimum_order_value_amount,minimum_order_value_currency\nAcme,500,\n",
        content_type="text/csv",
    )

    assert not report.valid
    assert report.errors[0].column == "minimum_order_value_currency"
    assert report.errors[0].reason == "currency is required when amount is supplied"


def test_commit_import_uses_single_transaction_and_skips_duplicates() -> None:
    report = ImportValidationReport(
        kind="suppliers",
        filename="suppliers.csv",
        row_count=2,
        rows=(
            SupplierImportRow(line=2, name="Acme"),
            SupplierImportRow(line=3, name="Existing"),
        ),
    )
    repository = FakeRepository(existing_supplier_names={"existing"})

    result = commit_import(report, repository, on_duplicate="skip")

    assert result.created == 1
    assert result.skipped == 1
    assert result.updated == 0
    assert repository.transactions_started == 1
    assert repository.transactions_committed == 1


def test_commit_import_rolls_back_when_a_write_fails() -> None:
    report = ImportValidationReport(
        kind="suppliers",
        filename="suppliers.csv",
        row_count=2,
        rows=(
            SupplierImportRow(line=2, name="Acme"),
            SupplierImportRow(line=3, name="Boom"),
        ),
    )
    repository = FakeRepository(fail_on_supplier="Boom")

    with pytest.raises(RuntimeError, match="write failed"):
        commit_import(report, repository)

    assert repository.created_suppliers == []
    assert repository.transactions_rolled_back == 1


class FakeTransaction:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository
        self.snapshot: list[str] = []

    def __enter__(self) -> FakeTransaction:
        self.repository.transactions_started += 1
        self.snapshot = list(self.repository.created_suppliers)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is None:
            self.repository.transactions_committed += 1
        else:
            self.repository.created_suppliers = self.snapshot
            self.repository.transactions_rolled_back += 1
        return False


class FakeRepository:
    def __init__(
        self,
        *,
        existing_supplier_names: set[str] | None = None,
        fail_on_supplier: str | None = None,
    ) -> None:
        self.existing_supplier_names = existing_supplier_names or set()
        self.fail_on_supplier = fail_on_supplier
        self.created_suppliers: list[str] = []
        self.transactions_started = 0
        self.transactions_committed = 0
        self.transactions_rolled_back = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def find_product_duplicate(self, row: object) -> object | None:
        return None

    def create_product(self, row: object) -> None:
        return None

    def update_product(self, duplicate: object, row: object) -> None:
        return None

    def find_supplier_duplicate(self, row: SupplierImportRow) -> object | None:
        return object() if row.name.casefold() in self.existing_supplier_names else None

    def create_supplier(self, row: SupplierImportRow) -> None:
        if row.name == self.fail_on_supplier:
            raise RuntimeError("write failed")
        self.created_suppliers.append(row.name)

    def update_supplier(self, duplicate: object, row: SupplierImportRow) -> None:
        return None
