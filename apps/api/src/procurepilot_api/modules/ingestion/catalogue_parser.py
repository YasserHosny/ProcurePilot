from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

import openpyxl

# T016 (research R6): header-name matching against an alias dictionary. product_name and
# unit_price are the columns R6 names as required. currency is ALSO effectively required here,
# beyond what R6 says explicitly — constitution non-negotiable #6 ("every monetary value stores
# an explicit currency") leaves no room for a silent default when a file has no currency column
# at all, so a missing currency column is a whole-file rejection alongside the other two.

_ALIASES: dict[str, tuple[str, ...]] = {
    "product_name": ("product_name", "name", "item", "description"),
    "unit_price": ("unit_price", "price", "rate"),
    "currency": ("currency", "curr"),
    "unit": ("unit", "uom", "unit_of_measure"),
    "minimum_order_quantity": ("qty", "quantity", "moq"),
}
_REQUIRED_FIELDS = ("product_name", "unit_price", "currency")
_CURRENCY_SHAPE = re.compile(r"^[A-Z]{3}$")


class CatalogueParseError(ValueError):
    """Whole-file rejection: raised when a required column cannot be resolved at all."""

    def __init__(self, message: str, *, unrecognised_columns: list[str] | None = None) -> None:
        super().__init__(message)
        self.unrecognised_columns = unrecognised_columns or []


@dataclass(frozen=True)
class CatalogueRow:
    # 1-based, counting the header as row 1 (matches how a spreadsheet user sees the file).
    row_number: int
    product_name: str
    unit_price_amount: Decimal
    unit_price_currency: str
    unit: str | None
    minimum_order_quantity: Decimal | None


@dataclass(frozen=True)
class CatalogueRowError:
    row_number: int
    column: str | None
    error: str


@dataclass(frozen=True)
class CatalogueImportData:
    valid_rows: list[CatalogueRow] = field(default_factory=list)
    error_rows: list[CatalogueRowError] = field(default_factory=list)
    column_mapping: dict[str, str] = field(default_factory=dict)
    total_rows: int = 0


def parse_catalogue_file(
    content: bytes, *, file_format: Literal["csv", "xlsx"]
) -> CatalogueImportData:
    raw_rows = _read_csv(content) if file_format == "csv" else _read_xlsx(content)
    if not raw_rows:
        raise CatalogueParseError("empty_file")

    header = raw_rows[0]
    mapping = _resolve_column_mapping(header)

    data_rows = raw_rows[1:]
    valid_rows: list[CatalogueRow] = []
    error_rows: list[CatalogueRowError] = []
    for offset, raw_row in enumerate(data_rows, start=2):
        row_dict = dict(zip(header, raw_row, strict=False))
        try:
            valid_rows.append(_parse_row(offset, row_dict, mapping))
        except _RowError as exc:
            error_rows.append(
                CatalogueRowError(row_number=offset, column=exc.column, error=exc.args[0])
            )

    return CatalogueImportData(
        valid_rows=valid_rows,
        error_rows=error_rows,
        column_mapping=mapping,
        total_rows=len(data_rows),
    )


class _RowError(ValueError):
    def __init__(self, message: str, *, column: str | None = None) -> None:
        super().__init__(message)
        self.column = column


def _resolve_column_mapping(header: list[str]) -> dict[str, str]:
    normalised_header = {_normalise_header(h): h for h in header if h}
    mapping: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalised_header:
                mapping[canonical] = normalised_header[alias]
                break

    missing_required = [f for f in _REQUIRED_FIELDS if f not in mapping]
    if missing_required:
        raise CatalogueParseError(
            f"required_columns_unmapped: {', '.join(missing_required)}",
            unrecognised_columns=missing_required,
        )
    return mapping


def _normalise_header(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def _parse_row(row_number: int, row: dict[str, str], mapping: dict[str, str]) -> CatalogueRow:
    product_name = (row.get(mapping["product_name"]) or "").strip()
    if not product_name:
        raise _RowError("missing_product_name", column=mapping["product_name"])

    price_raw = (row.get(mapping["unit_price"]) or "").strip()
    if not price_raw:
        raise _RowError("missing_unit_price", column=mapping["unit_price"])
    try:
        unit_price_amount = Decimal(price_raw)
    except InvalidOperation as exc:
        raise _RowError("unparseable_unit_price", column=mapping["unit_price"]) from exc
    if unit_price_amount <= 0:
        raise _RowError("unit_price_not_positive", column=mapping["unit_price"])

    currency_raw = (row.get(mapping["currency"]) or "").strip().upper()
    if not _CURRENCY_SHAPE.match(currency_raw):
        raise _RowError("invalid_currency_code", column=mapping["currency"])

    unit = None
    if "unit" in mapping:
        unit = (row.get(mapping["unit"]) or "").strip() or None

    minimum_order_quantity = None
    if "minimum_order_quantity" in mapping:
        moq_raw = (row.get(mapping["minimum_order_quantity"]) or "").strip()
        if moq_raw:
            try:
                minimum_order_quantity = Decimal(moq_raw)
            except InvalidOperation as exc:
                raise _RowError(
                    "unparseable_minimum_order_quantity",
                    column=mapping["minimum_order_quantity"],
                ) from exc
            if minimum_order_quantity <= 0:
                raise _RowError(
                    "minimum_order_quantity_not_positive",
                    column=mapping["minimum_order_quantity"],
                )

    return CatalogueRow(
        row_number=row_number,
        product_name=product_name,
        unit_price_amount=unit_price_amount,
        unit_price_currency=currency_raw,
        unit=unit,
        minimum_order_quantity=minimum_order_quantity,
    )


def _read_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if any(cell.strip() for cell in row)]


def _read_xlsx(content: bytes) -> list[list[str]]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows: list[list[str]] = []
    for row in sheet.iter_rows(values_only=True):
        if row is None or all(cell is None for cell in row):
            continue
        rows.append(["" if cell is None else str(cell) for cell in row])
    return rows
