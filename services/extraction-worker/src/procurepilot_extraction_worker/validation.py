from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from procurepilot_extraction_worker.models import ExtractedLine, ExtractionResult


@dataclass(frozen=True)
class ArithmeticValidation:
    status: str
    computed_total: Decimal | None
    stated_total: Decimal | None
    currency: str | None
    warnings: tuple[str, ...] = ()


def decimal_from_extracted(value: object) -> Decimal:
    return parse_decimal(str(value))


# Keep behaviorally identical to apps/api/src/procurepilot_api/modules/catalogue/csv_import.py
# parse_decimal; duplicated because the worker is a separate deployable with its own environment.
def parse_decimal(value: str) -> Decimal:
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


def validate_arithmetic(
    result: ExtractionResult,
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> ArithmeticValidation:
    currency = _currency(result)
    if result.stated_total is None:
        return ArithmeticValidation("not_applicable", None, None, currency)
    stated = _money_amount(result.stated_total.value)
    totals: list[Decimal] = []
    warnings: list[str] = []
    for line in result.lines:
        try:
            line_total = _line_total(line)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        if line_total is not None:
            totals.append(line_total)
    if not totals:
        return ArithmeticValidation("not_applicable", None, stated, currency, tuple(warnings))
    computed = sum(totals, Decimal("0"))
    status = _arithmetic_status(computed, stated, result.lines, tolerance)
    return ArithmeticValidation(status, computed, stated, currency, tuple(warnings))


def low_confidence_fields(result: ExtractionResult, threshold: float) -> list[str]:
    field_names: list[str] = []
    for field in result.header.values():
        if field.confidence < threshold:
            field_names.append(field.name)
    for line in result.lines:
        for field in line.fields.values():
            if field.confidence < threshold:
                field_names.append(f"line:{line.line_number}:{field.name}")
    if result.stated_total is not None and result.stated_total.confidence < threshold:
        field_names.append("stated_total")
    return field_names


def _line_total(line: ExtractedLine) -> Decimal | None:
    quantity = _field_decimal(line, "quantity")
    unit_price = _money_field_decimal(line, "unit_price")
    if quantity is None or unit_price is None:
        return None
    discount = _money_field_decimal(line, "discount") or Decimal("0")
    delivery_fee = _money_field_decimal(line, "delivery_fee") or Decimal("0")
    return (quantity * unit_price) - discount + delivery_fee


def _field_decimal(line: ExtractedLine, name: str) -> Decimal | None:
    field = line.fields.get(name)
    if field is None or field.value is None:
        return None
    return decimal_from_extracted(field.value)


def _money_field_decimal(line: ExtractedLine, name: str) -> Decimal | None:
    field = line.fields.get(name)
    if field is None:
        return None
    return _money_amount(field.value)


def _money_amount(value: object) -> Decimal:
    if not isinstance(value, dict) or "amount" not in value:
        raise ValueError("money field must be an object with amount")
    return decimal_from_extracted(value["amount"])


def _currency(result: ExtractionResult) -> str | None:
    currency = result.header.get("currency")
    if currency is not None and isinstance(currency.value, str):
        return currency.value
    if result.stated_total is not None and isinstance(result.stated_total.value, dict):
        value = result.stated_total.value.get("currency")
        return str(value) if value else None
    return None


def _arithmetic_status(
    subtotal: Decimal,
    stated: Decimal,
    lines: list[ExtractedLine],
    tolerance: Decimal,
) -> str:
    if abs(subtotal - stated) <= tolerance:
        return "reconciled"

    has_line_vat = any(
        line.fields.get("vat_rate") is not None
        and line.fields["vat_rate"].value is not None
        for line in lines
    )
    if has_line_vat or subtotal <= 0 or stated <= subtotal:
        return "mismatch"

    inferred_pct = round(float((stated - subtotal) / subtotal) * 100)
    if not 0 < inferred_pct <= 30:
        return "mismatch"

    recomputed = subtotal * (1 + Decimal(str(inferred_pct)) / 100)
    return "reconciled" if abs(recomputed - stated) <= tolerance else "mismatch"
