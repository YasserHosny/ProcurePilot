from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol
from uuid import UUID

ImportKind = Literal["products", "suppliers"]
DuplicateAction = Literal["skip", "update"]

ACCEPTED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
}
ACCEPTED_EXTENSIONS = (".csv",)

PRODUCT_REQUIRED_COLUMNS = frozenset({"tenant_name", "base_unit", "pack_count", "unit_size"})
PRODUCT_OPTIONAL_COLUMNS = frozenset(
    {"canonical_name", "brand", "variant", "gtin", "preferred_supplier_id"}
)
SUPPLIER_REQUIRED_COLUMNS = frozenset({"name"})
SUPPLIER_OPTIONAL_COLUMNS = frozenset(
    {
        "payment_terms",
        "lead_time_days",
        "minimum_order_value_amount",
        "minimum_order_value_currency",
        "delivery_fee_amount",
        "delivery_fee_currency",
        "status",
    }
)
SUPPLIER_STATUSES = frozenset({"active", "preferred", "blocked"})


class CsvImportError(ValueError):
    """Raised when a file must be refused before row parsing."""


@dataclass(frozen=True)
class ImportErrorDetail:
    line: int
    column: str | None
    reason: str


@dataclass(frozen=True)
class MoneyValue:
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ProductImportRow:
    line: int
    tenant_name: str
    base_unit: str
    pack_count: int
    unit_size: Decimal
    canonical_name: str | None = None
    brand: str | None = None
    variant: str | None = None
    gtin: str | None = None
    preferred_supplier_id: UUID | None = None

    @property
    def duplicate_key(self) -> str:
        return self.gtin or f"{self.canonical_name or self.tenant_name}|{self.base_unit}"


@dataclass(frozen=True)
class SupplierImportRow:
    line: int
    name: str
    payment_terms: str | None = None
    lead_time_days: int | None = None
    minimum_order_value: MoneyValue | None = None
    delivery_fee: MoneyValue | None = None
    status: Literal["active", "preferred", "blocked"] = "active"

    @property
    def duplicate_key(self) -> str:
        return self.name.casefold()


ImportRow = ProductImportRow | SupplierImportRow


@dataclass(frozen=True)
class ImportValidationReport:
    kind: ImportKind
    filename: str
    row_count: int
    rows: tuple[ImportRow, ...] = ()
    missing_columns: tuple[str, ...] = ()
    unrecognised_columns: tuple[str, ...] = ()
    duplicates: tuple[ImportErrorDetail, ...] = ()
    errors: tuple[ImportErrorDetail, ...] = ()
    file_error: str | None = None

    @property
    def valid(self) -> bool:
        return (
            self.file_error is None
            and not self.missing_columns
            and not self.unrecognised_columns
            and not self.errors
        )

    @property
    def preview(self) -> tuple[dict[str, object], ...]:
        return tuple(_row_preview(row) for row in self.rows)


@dataclass(frozen=True)
class ImportCommitResult:
    created: int
    skipped: int
    updated: int


class ImportTransaction(Protocol):
    def __enter__(self) -> ImportTransaction: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool | None: ...


class ImportRepository(Protocol):
    """Persistence adapter used by the router/service layer.

    Implementations must make `transaction()` return a real database transaction. The commit
    function below deliberately knows nothing about SQL client details.
    """

    def transaction(self) -> AbstractContextManager[Any]: ...

    def find_product_duplicate(self, row: ProductImportRow) -> object | None: ...

    def create_product(self, row: ProductImportRow) -> None: ...

    def update_product(self, duplicate: object, row: ProductImportRow) -> None: ...

    def find_supplier_duplicate(self, row: SupplierImportRow) -> object | None: ...

    def create_supplier(self, row: SupplierImportRow) -> None: ...

    def update_supplier(self, duplicate: object, row: SupplierImportRow) -> None: ...


def validate_import_file(
    *,
    kind: ImportKind,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> ImportValidationReport:
    """Validate a CSV import and return a preview report without writing anything."""

    file_error = _pre_parse_file_error(filename, content, content_type)
    if file_error is not None:
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            file_error=file_error,
        )

    try:
        text = _decode_csv(content)
    except CsvImportError:
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            file_error="not an accepted CSV file type",
        )
    if text == "":
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            file_error="empty file",
        )

    return _validate_csv_text(kind=kind, filename=filename, text=text)


def parse_decimal(value: str) -> Decimal:
    """Parse an unambiguous decimal string without using float or locale guesses."""

    raw = value.strip()
    if raw == "":
        raise ValueError("decimal value is required")

    if "," in raw and "." in raw:
        decimal_separator = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        normalised = raw.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in raw:
        raise ValueError("ambiguous decimal separator in value with comma but no dot")
    else:
        normalised = raw

    try:
        return Decimal(normalised)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal value") from exc


def commit_import(
    report: ImportValidationReport,
    repository: ImportRepository,
    *,
    on_duplicate: DuplicateAction = "skip",
    after_rows: Callable[[ImportRepository], None] | None = None,
) -> ImportCommitResult:
    """Commit an already validated report in a single repository transaction."""

    if on_duplicate not in {"skip", "update"}:
        raise ValueError("on_duplicate must be 'skip' or 'update'")
    if not report.valid:
        raise ValueError("cannot commit an invalid import report")

    created = 0
    skipped = 0
    updated = 0

    with repository.transaction():
        for row in report.rows:
            if isinstance(row, ProductImportRow):
                duplicate = repository.find_product_duplicate(row)
                if duplicate is None:
                    repository.create_product(row)
                    created += 1
                elif on_duplicate == "skip":
                    skipped += 1
                else:
                    repository.update_product(duplicate, row)
                    updated += 1
            else:
                duplicate = repository.find_supplier_duplicate(row)
                if duplicate is None:
                    repository.create_supplier(row)
                    created += 1
                elif on_duplicate == "skip":
                    skipped += 1
                else:
                    repository.update_supplier(duplicate, row)
                    updated += 1
        if after_rows is not None:
            after_rows(repository)

    return ImportCommitResult(created=created, skipped=skipped, updated=updated)


def _validate_csv_text(*, kind: ImportKind, filename: str, text: str) -> ImportValidationReport:
    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream)
    headers = reader.fieldnames
    if headers is None:
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            file_error="empty file",
        )

    normalised_headers = [_normalise_header(header) for header in headers]
    missing_columns, unrecognised_columns = _column_errors(kind, normalised_headers)
    if missing_columns or unrecognised_columns:
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            missing_columns=tuple(missing_columns),
            unrecognised_columns=tuple(unrecognised_columns),
        )

    rows: list[ImportRow] = []
    errors: list[ImportErrorDetail] = []
    previous_line = reader.line_num
    for raw_row in reader:
        line = previous_line + 1
        previous_line = reader.line_num
        row = {
            _normalise_header(column): value
            for column, value in raw_row.items()
            if column is not None
        }
        overflow = raw_row.get(None)
        if overflow:
            errors.append(
                ImportErrorDetail(
                    line=line,
                    column=None,
                    reason="row has more values than header columns",
                )
            )
            continue
        parsed = (
            _parse_product_row(line, row, errors)
            if kind == "products"
            else _parse_supplier_row(line, row, errors)
        )
        if parsed is not None:
            rows.append(parsed)

    if not rows and not errors:
        return ImportValidationReport(
            kind=kind,
            filename=filename,
            row_count=0,
            file_error="header-only file",
        )

    duplicate_errors = _file_duplicate_errors(rows)
    return ImportValidationReport(
        kind=kind,
        filename=filename,
        row_count=len(rows) + len(errors),
        rows=tuple(rows),
        duplicates=tuple(duplicate_errors),
        errors=tuple(errors),
    )


def _parse_product_row(
    line: int,
    row: dict[str, str | None],
    errors: list[ImportErrorDetail],
) -> ProductImportRow | None:
    before = len(errors)
    tenant_name = _required_text(line, row, "tenant_name", errors)
    base_unit = _required_text(line, row, "base_unit", errors)
    pack_count = _positive_int(line, row.get("pack_count"), "pack_count", errors)
    unit_size = _positive_decimal(line, row.get("unit_size"), "unit_size", errors)
    preferred_supplier_id = _optional_uuid(
        line,
        row.get("preferred_supplier_id"),
        "preferred_supplier_id",
        errors,
    )

    if len(errors) > before:
        return None

    return ProductImportRow(
        line=line,
        tenant_name=tenant_name,
        base_unit=base_unit,
        pack_count=pack_count,
        unit_size=unit_size,
        canonical_name=_optional_text(row.get("canonical_name")),
        brand=_optional_text(row.get("brand")),
        variant=_optional_text(row.get("variant")),
        gtin=_optional_text(row.get("gtin")),
        preferred_supplier_id=preferred_supplier_id,
    )


def _parse_supplier_row(
    line: int,
    row: dict[str, str | None],
    errors: list[ImportErrorDetail],
) -> SupplierImportRow | None:
    before = len(errors)
    name = _required_text(line, row, "name", errors)
    lead_time_days = _non_negative_int(line, row.get("lead_time_days"), "lead_time_days", errors)
    minimum_order_value = _money_value(
        line,
        row.get("minimum_order_value_amount"),
        row.get("minimum_order_value_currency"),
        "minimum_order_value",
        errors,
    )
    delivery_fee = _money_value(
        line,
        row.get("delivery_fee_amount"),
        row.get("delivery_fee_currency"),
        "delivery_fee",
        errors,
    )
    status = _optional_text(row.get("status")) or "active"
    if status not in SUPPLIER_STATUSES:
        errors.append(
            ImportErrorDetail(
                line=line,
                column="status",
                reason="status must be active, preferred, or blocked",
            )
        )

    if len(errors) > before:
        return None

    return SupplierImportRow(
        line=line,
        name=name,
        payment_terms=_optional_text(row.get("payment_terms")),
        lead_time_days=lead_time_days,
        minimum_order_value=minimum_order_value,
        delivery_fee=delivery_fee,
        status=status,  # type: ignore[arg-type]
    )


def _pre_parse_file_error(
    filename: str,
    content: bytes,
    content_type: str | None,
) -> str | None:
    if not filename.casefold().endswith(ACCEPTED_EXTENSIONS):
        return "not an accepted CSV file type"
    if content_type and content_type.split(";")[0].strip().casefold() not in ACCEPTED_CONTENT_TYPES:
        return "not an accepted CSV file type"
    if _looks_binary(content):
        return "not an accepted CSV file type"
    return None


def _decode_csv(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("not an accepted CSV file type") from exc


def _looks_binary(content: bytes) -> bool:
    sample = content[:1024]
    return b"\x00" in sample


def _column_errors(kind: ImportKind, headers: Iterable[str]) -> tuple[list[str], list[str]]:
    header_set = set(headers)
    if kind == "products":
        required = PRODUCT_REQUIRED_COLUMNS
        allowed = PRODUCT_REQUIRED_COLUMNS | PRODUCT_OPTIONAL_COLUMNS
    else:
        required = SUPPLIER_REQUIRED_COLUMNS
        allowed = SUPPLIER_REQUIRED_COLUMNS | SUPPLIER_OPTIONAL_COLUMNS

    return sorted(required - header_set), sorted(header_set - allowed)


def _required_text(
    line: int,
    row: dict[str, str | None],
    column: str,
    errors: list[ImportErrorDetail],
) -> str:
    value = _optional_text(row.get(column))
    if value is None:
        errors.append(ImportErrorDetail(line=line, column=column, reason="value is required"))
        return ""
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
) -> int:
    parsed = _int_value(line, value, column, errors, required=True)
    if parsed is not None and parsed <= 0:
        errors.append(
            ImportErrorDetail(line=line, column=column, reason="value must be greater than zero")
        )
    return parsed or 0


def _non_negative_int(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
) -> int | None:
    parsed = _int_value(line, value, column, errors, required=False)
    if parsed is not None and parsed < 0:
        errors.append(
            ImportErrorDetail(line=line, column=column, reason="value must be zero or greater")
        )
    return parsed


def _int_value(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
    *,
    required: bool,
) -> int | None:
    text = _optional_text(value)
    if text is None:
        if required:
            errors.append(ImportErrorDetail(line=line, column=column, reason="value is required"))
        return None
    try:
        return int(text)
    except ValueError:
        errors.append(
            ImportErrorDetail(line=line, column=column, reason="value must be an integer")
        )
        return None


def _positive_decimal(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
) -> Decimal:
    parsed = _decimal_value(line, value, column, errors, required=True)
    if parsed is not None and parsed <= 0:
        errors.append(
            ImportErrorDetail(line=line, column=column, reason="value must be greater than zero")
        )
    return parsed or Decimal("0")


def _decimal_value(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
    *,
    required: bool,
) -> Decimal | None:
    text = _optional_text(value)
    if text is None:
        if required:
            errors.append(ImportErrorDetail(line=line, column=column, reason="value is required"))
        return None
    try:
        return parse_decimal(text)
    except ValueError as exc:
        errors.append(ImportErrorDetail(line=line, column=column, reason=str(exc)))
        return None


def _money_value(
    line: int,
    amount: str | None,
    currency: str | None,
    column_prefix: str,
    errors: list[ImportErrorDetail],
) -> MoneyValue | None:
    amount_text = _optional_text(amount)
    currency_text = _optional_text(currency)
    if amount_text is None and currency_text is None:
        return None
    if amount_text is None:
        errors.append(
            ImportErrorDetail(
                line=line,
                column=f"{column_prefix}_amount",
                reason="amount is required when currency is supplied",
            )
        )
        return None
    if currency_text is None:
        errors.append(
            ImportErrorDetail(
                line=line,
                column=f"{column_prefix}_currency",
                reason="currency is required when amount is supplied",
            )
        )
        return None

    parsed_amount = _decimal_value(
        line,
        amount_text,
        f"{column_prefix}_amount",
        errors,
        required=True,
    )
    if parsed_amount is None:
        return None
    currency_code = currency_text.upper()
    if len(currency_code) != 3 or not currency_code.isalpha():
        errors.append(
            ImportErrorDetail(
                line=line,
                column=f"{column_prefix}_currency",
                reason="currency must be a three-letter ISO code",
            )
        )
        return None
    return MoneyValue(amount=parsed_amount, currency=currency_code)


def _optional_uuid(
    line: int,
    value: str | None,
    column: str,
    errors: list[ImportErrorDetail],
) -> UUID | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return UUID(text)
    except ValueError:
        errors.append(ImportErrorDetail(line=line, column=column, reason="value must be a UUID"))
        return None


def _file_duplicate_errors(rows: Iterable[ImportRow]) -> list[ImportErrorDetail]:
    first_seen: dict[tuple[type[ImportRow], str], int] = {}
    errors: list[ImportErrorDetail] = []
    for row in rows:
        key = (type(row), row.duplicate_key)
        first_line = first_seen.get(key)
        if first_line is None:
            first_seen[key] = row.line
            continue
        errors.append(
            ImportErrorDetail(
                line=row.line,
                column=None,
                reason=f"duplicate row in file; first seen on line {first_line}",
            )
        )
    return errors


def _normalise_header(header: str) -> str:
    return header.strip().removeprefix("\ufeff").casefold()


def _row_preview(row: ImportRow) -> dict[str, object]:
    if isinstance(row, ProductImportRow):
        return {
            "line": row.line,
            "tenant_name": row.tenant_name,
            "canonical_name": row.canonical_name,
            "brand": row.brand,
            "variant": row.variant,
            "gtin": row.gtin,
            "base_unit": row.base_unit,
            "pack": {
                "pack_count": row.pack_count,
                "unit_size": str(row.unit_size),
            },
            "preferred_supplier_id": str(row.preferred_supplier_id)
            if row.preferred_supplier_id
            else None,
        }
    return {
        "line": row.line,
        "name": row.name,
        "payment_terms": row.payment_terms,
        "lead_time_days": row.lead_time_days,
        "minimum_order_value": _money_preview(row.minimum_order_value),
        "delivery_fee": _money_preview(row.delivery_fee),
        "status": row.status,
    }


def _money_preview(value: MoneyValue | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": str(value.amount), "currency": value.currency}
