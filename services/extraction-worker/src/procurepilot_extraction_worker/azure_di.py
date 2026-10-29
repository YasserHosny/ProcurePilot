from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, NamedTuple

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from procurepilot_extraction_worker.currency import (
    _EGP_MARKER,
    _EUR_MARKER,
    _OTHER_MARKER,
    _SAR_MARKER,
    _adjacent_to_number,
    detect_currency,
    parse_localised_decimal,
)
from procurepilot_extraction_worker.models import (
    ExtractedField,
    ExtractedLine,
    ExtractionResult,
)
from procurepilot_extraction_worker.providers import ExtractionProviderError
from procurepilot_extraction_worker.settings import WorkerSettings, get_settings

MODEL_ID = "prebuilt-invoice"

_PERCENTAGE_PATTERN = re.compile(
    r"(?:"
    r"[\d٠-٩۰-۹][\d٠-٩۰-۹.,٬٫]*\s*[%٪\u066a](?![\d٠-٩۰-۹])"
    r"|"
    r"[%٪\u066a]\s*[\d٠-٩۰-۹]{1,3}(?:[.,٫][\d٠-٩۰-۹]{1,2})?(?![.,٬٫\d٠-٩۰-۹])"
    r")",
    re.IGNORECASE,
)
_TOTAL_ROW_RE = re.compile(
    r"^[\s:：\-–]*(?:(?:[\d.,:：()（）/\\\-_%٪\u066a]+|ر\.?\s*س\.?|SAR|SR|ج\.م|LE|EGP|\$|£|€)\s*)*"
    r"(?:(?:لل|[وبفل])?(?:الاجمالي|اجمالي|االجمايل|المجموع|مجموع)|grand\s+total|total)"
    r"(?![^\W\d_])"
    r"(?!\s*(?:ال)?فرعي(?![^\W\d_]))",
    re.IGNORECASE,
)
_BEFORE_TAX_SUBTOTAL_RE = re.compile(
    r"^[\s:：\-–]*(?:(?:[\d.,:：()（）/\\\-_%٪\u066a]+|ر\.?\s*س\.?|SAR|SR|ج\.م|LE|EGP|\$|£|€)\s*)*"
    r"(?:sub[\s\-]*total|(?:لل|[وبفل])?(?:ال)?(?:مجموع|اجمالي)\s+(?:ال)?فرعي)(?![^\W\d_])",
    re.IGNORECASE,
)
_PACK_TEXT_RE = re.compile(
    r"(?:[^\W\d_]+\s+)*"  # Optional container words; never infer a size from the container.
    r"(?:(?P<count>\d+)\s*[×x]\s*)?"
    r"(?P<size>\d+(?:[.٫]\d+)?)\s*(?P<unit>[^\W\d_]+)"
    r"(?:\s+[^\W\d_]+)*"  # English quotes also print the container after the size.
)
_PACK_UNITS = {
    "kg": "kilogram",
    "kgs": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "كجم": "kilogram",
    "كيلو": "kilogram",
    "كيلوجرام": "kilogram",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "جم": "gram",
    "جرام": "gram",
    "l": "litre",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "لتر": "litre",
    "ml": "millilitre",
    "millilitre": "millilitre",
    "millilitres": "millilitre",
    "milliliter": "millilitre",
    "milliliters": "millilitre",
    "مل": "millilitre",
    "مليلتر": "millilitre",
}


class ParsedPack(NamedTuple):
    pack_count: int
    unit_size: Decimal
    pack_unit: str


def parse_pack_text(text: str) -> ParsedPack | None:
    """Parse a printed size or count × size, in base units (grams to kg, millilitres to L)."""
    match = _PACK_TEXT_RE.fullmatch(_normalise_header(text).strip())
    if match is None:
        return None
    unit = _PACK_UNITS.get(match["unit"])
    if unit is None:
        return None
    count = int(match["count"]) if match["count"] is not None else 1
    size = parse_localised_decimal(match["size"])
    if count <= 0 or size <= 0:
        return None
    if unit == "gram":
        unit = "kilogram"
        size = size / Decimal(1000)
    elif unit == "millilitre":
        unit = "litre"
        size = size / Decimal(1000)
    return ParsedPack(count, size, unit)


class AzureDocumentIntelligenceProvider:
    method = "azure_di"
    model_version = f"{MODEL_ID}:2024-11-30"

    def __init__(
        self, settings: WorkerSettings | None = None, client: object | None = None
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    def extract(
        self,
        *,
        document_id: str,
        mime_type: str,
        storage_path: str,
        document_bytes: bytes | None = None,
    ) -> ExtractionResult:
        if document_bytes is None:
            raise ExtractionProviderError("document_bytes required for Azure DI extraction")

        endpoint = self._settings.azure_di_endpoint
        key = self._settings.azure_di_key
        if self._client is None and (not endpoint or not key):
            raise ExtractionProviderError("AZURE_DI_ENDPOINT and AZURE_DI_KEY are required")

        client = self._client or DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )

        try:
            poller = client.begin_analyze_document(
                MODEL_ID,
                AnalyzeDocumentRequest(bytes_source=document_bytes),
            )
            result = poller.result()
            parsed = _parse_invoice_result(result, self.model_version)
            if parsed.expected_line_count is not None:
                return parsed
            layout = client.begin_analyze_document(
                "prebuilt-layout", AnalyzeDocumentRequest(bytes_source=document_bytes)
            ).result()
            table_result = _parse_invoice_result(layout, "prebuilt-layout:2024-11-30")
            if table_result.expected_line_count is not None:
                return _merge_headers(parsed, table_result, invoice_total=parsed.stated_total)
            return parsed
        except Exception as exc:
            raise ExtractionProviderError(f"Azure DI analysis failed: {exc}") from exc


def _parse_invoice_result(result: object, model_version: str) -> ExtractionResult:
    header: dict[str, ExtractedField] = {}
    lines: list[ExtractedLine] = []
    stated_total: ExtractedField | None = None

    table_result = _parse_line_table(result, model_version)
    documents = _get(result, "documents", []) or []
    if not documents:
        return table_result or ExtractionResult("azure_di", model_version, {}, [], cost_usd=0.0)

    doc = documents[0]
    fields = _get(doc, "fields", {}) or {}

    vendor = _content(fields, "VendorName")
    if vendor:
        header["supplier_name"] = _make_field("supplier_name", vendor, fields, "VendorName")

    currency_text = _all_document_text(result)
    currency, currency_conflict = _infer_currency_state(fields)
    if currency_conflict or _has_currency_conflict(currency_text):
        currency = None
    else:
        currency = currency or detect_currency(currency_text)
    if currency is not None:
        header["currency"] = ExtractedField("currency", currency, 0.90, 1, None)

    invoice_date = _date_evidence(fields, "InvoiceDate")
    if invoice_date:
        header["issue_date"] = _make_field(
            "issue_date",
            invoice_date,
            fields,
            "InvoiceDate",
            typed_value=_typed_date(fields, "InvoiceDate"),
        )

    due_date = _date_evidence(fields, "DueDate")
    if due_date:
        header["expiry_date"] = _make_field(
            "expiry_date",
            due_date,
            fields,
            "DueDate",
            typed_value=_typed_date(fields, "DueDate"),
        )
    else:
        validity = _find_validity_date(currency_text)
        if validity:
            # prebuilt-invoice has no "valid until" field and maps it to DueDate only
            # sometimes (finding 42: never on a photo); text evidence goes to review.
            header["expiry_date"] = ExtractedField(
                "expiry_date", validity, _TEXT_VALIDITY_CONFIDENCE, 1, None
            )

    total_content = _content(fields, "InvoiceTotal")
    if total_content is not None:
        amount = _clean_number(total_content)
        if amount:
            stated_total = ExtractedField(
                "stated_total",
                {"amount": amount, "currency": currency},
                _confidence(fields, "InvoiceTotal") or 0.85,
                1,
                None,
            )

    items_field = fields.get("Items")
    if table_result is not None:
        return _merge_headers(
            ExtractionResult("azure_di", model_version, header, [], stated_total, 0.0),
            table_result,
            invoice_total=stated_total,
        )
    if items_field:
        item_list = _get(items_field, "value_array", []) or []
        for idx, item in enumerate(item_list, start=1):
            item_fields = _get(item, "value_object", {}) or {}
            line = _parse_line_item(idx, item_fields, currency)
            lines.append(line)

    return ExtractionResult(
        method="azure_di",
        model_version=model_version,
        header=header,
        lines=lines,
        stated_total=stated_total,
        cost_usd=0.0,
    )


def _parse_line_table(result: object, model_version: str) -> ExtractionResult | None:
    """Prefer semantic-header table rows; invoice fields remain the source for header data.

    Provider policy: analyze prebuilt-invoice first; if it has a line table, ignore Items.
    Otherwise analyze prebuilt-layout and use its table when found, falling back to Items only
    when neither model exposes a usable table. A table/paragraph total overrides InvoiceTotal.
    """
    tables = _get(result, "tables", []) or []
    document_text = _all_document_text(result)
    all_cell_text = " ".join(
        str(_get(c, "content", "") or "") for t in tables for c in (_get(t, "cells", []) or [])
    )
    currency = detect_currency(all_cell_text + " " + document_text)
    currency_conflict = _has_currency_conflict(all_cell_text + " " + document_text)
    lines: list[ExtractedLine] = []
    expected = 0
    stated_total = None
    before_tax_total = None
    previous_col_roles: dict[int, str] | None = None
    previous_column_count: int | None = None
    charge_amount: Decimal | None = None
    for table in tables:
        cells = _get(table, "cells", []) or []
        rows: dict[int, list[object]] = {}
        for cell in cells:
            rows.setdefault(int(_get(cell, "rowIndex", _get(cell, "row_index", 0))), []).append(
                cell
            )
        roles_by_row: dict[int, dict[str, object]] = {}
        for row, row_cells in rows.items():
            roles: dict[str, object] = {}
            for cell in row_cells:
                role = _header_role(str(_get(cell, "content", "") or ""))
                if role and role not in roles:
                    roles[role] = cell
            if {"description", "quantity"} <= roles.keys() and (
                {"unit_price", "line_total"} & roles.keys()
            ):
                roles_by_row[row] = roles
        column_count = int(_get(table, "columnCount", 0) or 0)
        header_row: int | None = None
        if roles_by_row:
            header_row = max(roles_by_row, key=lambda row: (len(roles_by_row[row]), -row))
            roles = roles_by_row[header_row]
            col_roles: dict[int, str] = {}
            for role, cell in roles.items():
                start = int(_get(cell, "columnIndex", _get(cell, "column_index", 0)))
                span = int(_get(cell, "columnSpan", _get(cell, "column_span", 1)) or 1)
                for column in range(start, start + span):
                    col_roles[column] = role
            previous_col_roles = col_roles
            previous_column_count = column_count
        elif (
            previous_col_roles is not None
            and previous_column_count == column_count
            and previous_column_count is not None
        ):
            col_roles = previous_col_roles
            header_row = min(rows, default=0) - 1
        else:
            continue
        for row in sorted(r for r in rows if r > header_row):
            row_cells = rows[row]
            data: dict[str, str] = {}
            expanded: dict[int, str] = {}
            role_cells: dict[str, object] = {}
            for cell in row_cells:
                value = str(_get(cell, "content", "") or "").strip()
                start = int(_get(cell, "columnIndex", _get(cell, "column_index", 0)))
                span = int(_get(cell, "columnSpan", _get(cell, "column_span", 1)) or 1)
                for column in range(start, start + span):
                    expanded[column] = value
                    role = col_roles.get(column)
                    if role and value:
                        if role not in data:
                            data[role] = value
                            role_cells[role] = cell
            desc = data.get("description", "").replace("\n", " ").strip()
            qty_raw = data.get("quantity", "")
            price_raw = data.get("unit_price", "")
            desc_cell = role_cells.get("description")
            if desc_cell is not None:
                if _same_cell(role_cells.get("quantity"), desc_cell):
                    qty_raw = ""
                if _same_cell(role_cells.get("unit_price"), desc_cell):
                    price_raw = ""
            qty = _clean_number(qty_raw)
            price = _clean_number(price_raw)
            total = _clean_number(data.get("line_total", ""))
            label = " ".join(
                value.replace("\n", " ").strip()
                for value in dict.fromkeys(expanded.values())
                if value and _numeric_cell_amount(value) is None
            )
            desc = desc or label
            numeric_amounts: list[str] = []
            for col in sorted(expanded.keys()):
                val_clean = _PERCENTAGE_PATTERN.sub("", expanded[col]).strip()
                amt = _numeric_cell_amount(val_clean)
                if amt is not None:
                    numeric_amounts.append(amt)
            fallback_amount = total or (numeric_amounts[-1] if numeric_amounts else None)
            is_total = (
                qty is None
                and not (price and total)
                and (_is_total_row(label) or _is_total_row(desc))
            )
            if is_total and fallback_amount is None:
                sorted_cols = sorted(expanded.keys(), reverse=True)

                def _cell_amount(text: str) -> str | None:
                    clean = _PERCENTAGE_PATTERN.sub("", text).strip()
                    amts = re.findall(r"[\d٠-٩۰-۹][\d٠-٩۰-۹.,٬٫]*", clean)
                    if amts:
                        return _clean_number(amts[-1])
                    return None

                for col in sorted_cols:
                    val = expanded[col]
                    if _is_total_row(val) or (bool(desc) and val == desc):
                        continue
                    if (
                        _SAR_MARKER.search(val)
                        or _EUR_MARKER.search(val)
                        or _EGP_MARKER.search(val)
                        or _OTHER_MARKER.search(val)
                    ):
                        amt = _cell_amount(val)
                        if amt:
                            fallback_amount = amt
                            break

                if fallback_amount is None:
                    for col in sorted_cols:
                        val = expanded[col]
                        if _is_total_row(val) or (bool(desc) and val == desc):
                            continue
                        amt = _cell_amount(val)
                        if amt:
                            fallback_amount = amt
                            break

                if fallback_amount is None:
                    for col in sorted_cols:
                        val = expanded[col]
                        amt = _cell_amount(val)
                        if amt:
                            fallback_amount = amt
                            break
            if is_total:
                amount = fallback_amount or price
                if amount:
                    candidate = _money_field("stated_total", amount, currency, 0.9)
                    if _is_before_tax_row(label) or _is_before_tax_row(desc):
                        before_tax_total = candidate
                    else:
                        stated_total = candidate
                continue
            if qty is None and (_is_subtotal_row(label) or _is_subtotal_row(desc)):
                continue
            if qty is None and _is_tax_row(label):
                continue
            if qty is None and _is_charge_row(label):
                amount = fallback_amount or price
                if amount:
                    charge_amount = (charge_amount or Decimal("0")) + Decimal(amount)
                continue
            if not desc:
                continue
            expected += 1
            if qty is None or price is None:
                continue
            confidence = 0.90
            line_fields = {
                "quantity": ExtractedField("quantity", qty, confidence),
                "unit_price": _money_field("unit_price", price, currency, confidence),
            }
            if data.get("unit"):
                line_fields["pack_unit"] = ExtractedField("pack_unit", data["unit"], confidence)
            if total:
                line_fields["line_total"] = _money_field("line_total", total, currency, confidence)
                if abs(Decimal(qty) * Decimal(price) - Decimal(total)) > Decimal("0.01"):
                    confidence = 0.50
                    line_fields["quantity"] = ExtractedField("quantity", qty, confidence)
                    line_fields["unit_price"] = _money_field(
                        "unit_price", price, currency, confidence
                    )
            if "pack" in data:
                pack = parse_pack_text(data["pack"])
                if pack is None:
                    line_fields["pack_text"] = ExtractedField("pack_text", data["pack"], 0.4)
                else:
                    line_fields["pack_count"] = ExtractedField(
                        "pack_count", pack.pack_count, confidence
                    )
                    line_fields["unit_size"] = ExtractedField(
                        "unit_size", format(pack.unit_size, "f"), confidence
                    )
                    line_fields["pack_unit"] = ExtractedField(
                        "pack_unit", pack.pack_unit, confidence
                    )
            lines.append(ExtractedLine(len(lines) + 1, desc, line_fields))
    if charge_amount and lines:
        # The existing arithmetic model adds a line's delivery fee once, so attach a
        # document-level charge to the final item rather than creating a pseudo-item.
        last = lines[-1]
        last.fields["delivery_fee"] = _money_field(
            "delivery_fee", format(charge_amount, "f"), currency, 0.9
        )
    if expected == 0:
        return None
    if before_tax_total is not None:
        stated_total = before_tax_total
    paragraph_total = _find_grand_total(document_text, currency)
    if paragraph_total is not None and (
        stated_total is None or _has_before_tax_total(document_text)
    ):
        stated_total = paragraph_total
    header = (
        {"currency": ExtractedField("currency", currency, 0.9)}
        if currency and not currency_conflict
        else {}
    )
    if currency_conflict:
        for line in lines:
            for key in ("unit_price", "line_total", "delivery_fee"):
                if key in line.fields:
                    value = dict(line.fields[key].value)
                    value["currency"] = None
                    line.fields[key] = ExtractedField(key, value, line.fields[key].confidence)
        if stated_total:
            stated_total = ExtractedField(
                "stated_total",
                {"amount": stated_total.value["amount"], "currency": None},
                stated_total.confidence,
            )
    return ExtractionResult(
        "azure_di", model_version, header, lines, stated_total, 0.0, expected_line_count=expected
    )


def _same_cell(c1: object | None, c2: object | None) -> bool:
    if c1 is None or c2 is None:
        return False
    if c1 is c2:
        return True
    span1 = int(_get(c1, "columnSpan", _get(c1, "column_span", 1)) or 1)
    span2 = int(_get(c2, "columnSpan", _get(c2, "column_span", 1)) or 1)
    if span1 > 1 or span2 > 1:
        start1 = int(_get(c1, "columnIndex", _get(c1, "column_index", 0)))
        start2 = int(_get(c2, "columnIndex", _get(c2, "column_index", 0)))
        if (start1, span1) == (start2, span2):
            return True
        spans1 = _get(c1, "spans")
        spans2 = _get(c2, "spans")
        if spans1 and spans2 and spans1 == spans2:
            return True
    return False


def _get(obj: object, name: str, default: Any = None) -> Any:  # noqa: ANN401
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), name)
        return obj.get(camel, default)
    snake = re.sub(r"[A-Z]", lambda m: "_" + m.group().lower(), name)
    camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), name)
    return getattr(obj, name, getattr(obj, snake, getattr(obj, camel, default)))


def _header_role(text: str) -> str | None:
    n = _normalise_header(text)
    compact = re.sub(r"\s+", "", n)
    candidates = [
        (
            "unit_price",
            (
                "سعر الوحدة",
                "سعر العبوة",
                "سعر",
                "الفئة",
                "unit price",
                "unitprice",
                "price",
                "rate",
            ),
        ),
        ("line_total", ("الإجمالي", "القيمة", "المبلغ", "total", "amount")),
        (
            "description",
            ("الصنف والمواصفات", "الصنف", "البيان", "الوصف", "item", "description", "product"),
        ),
        ("quantity", ("الكمية", "العدد", "quantity", "qty")),
        ("unit", ("الوحدة", "unit", "uom")),
        ("pack", ("العبوة", "التعبئة", "الحجم", "pack", "packing", "pack size", "packaging")),
    ]
    matches: list[tuple[int, str]] = []
    for role, words in candidates:
        # A pack word must not take over an existing price, quantity, unit or total header.
        if role == "pack" and matches:
            break
        for word in words:
            wn = _normalise_header(word)
            if wn in n or re.sub(r"\s+", "", wn) in compact:
                matches.append((len(wn), role))
            elif _skeleton(wn) and _skeleton(wn) in _skeleton(n):
                matches.append((len(wn), role))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def _normalise_header(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(
        r"[\u0610-\u061a\u064b-\u065f\u0670\u0640\u06d6-\u06ed\u200e\u200f\u202a-\u202e\u2066-\u2069]",
        "",
        text,
    )
    return text.translate(str.maketrans("أإآٱىئة", "اااايي ه".replace(" ", ""))).lower()


def _skeleton(text: str) -> str:
    return re.sub(r"[ال\s]", "", _normalise_header(text))


def _is_total_row(desc: str) -> bool:
    n = _normalise_header(desc).strip()
    return _TOTAL_ROW_RE.search(n) is not None


def _is_before_tax_row(desc: str) -> bool:
    n = _normalise_header(desc)
    return "قبل الضريبه" in n or "before tax" in n


def _is_subtotal_row(desc: str) -> bool:
    n = _normalise_header(desc).strip()
    return _BEFORE_TAX_SUBTOTAL_RE.search(n) is not None


def _is_tax_row(desc: str) -> bool:
    n = _normalise_header(desc)
    return "ضريبه" in n or re.search(r"\bvat\b|\btax\b", n, re.I) is not None


def _is_charge_row(desc: str) -> bool:
    n = _normalise_header(desc)
    return any(
        _normalise_header(x) in n
        for x in (
            "مصاريف نقل",
            "مصاريف توصيل",
            "نقل",
            "توصيل",
            "شحن",
            "delivery",
            "shipping",
            "freight",
        )
    )


def _money_field(name: str, amount: str, currency: str | None, confidence: float) -> ExtractedField:
    return ExtractedField(name, {"amount": amount, "currency": currency}, confidence)


def _all_document_text(result: object) -> str:
    parts = [str(_get(result, "content", "") or "")]
    parts.extend(str(_get(p, "content", "") or "") for p in (_get(result, "paragraphs", []) or []))
    for page in _get(result, "pages", []) or []:
        parts.extend(
            str(_get(line, "content", "") or "") for line in (_get(page, "lines", []) or [])
        )
    return "\n".join(parts)


_TEXT_VALIDITY_CONFIDENCE = 0.6
_VALIDITY_LABEL = (
    r"(?:(?:العرض\s+)?(?:صالح|ساري)[ةه]?\s+حت[ىي]|(?:ال)?صلاحي[ةه](?:\s+العرض)?(?:\s+حت[ىي])?|"
    r"تاريخ\s+(?:الانتهاء|انتهاء\s+العرض)|valid\s+(?:until|till|thru|through)|"
    r"validity(?:\s+date)?|expiry\s+date|expires(?:\s+on)?)"
)
_TEXT_DATE = r"\d{1,4}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}"
_VALIDITY_AFTER = re.compile(rf"{_VALIDITY_LABEL}\s*[:：]\s*({_TEXT_DATE})", re.I)
_VALIDITY_AFTER_LOOSE = re.compile(
    rf"{_VALIDITY_LABEL}\s*[\-–]?\s*({_TEXT_DATE})(?!\d)(?!\s*[:：])", re.I
)
# OCR of a photo can emit an RTL line in visual order ("29/10/2026 :صالح حتى 19/10/2026 ..."),
# putting the value before its label. Only the label's own colon, right next to the date, makes
# it the label's value; "Date: 19/10/2026 Validity: 30 days" must not yield the issue date.
_VALIDITY_BEFORE = re.compile(rf"({_TEXT_DATE})\s*[:：]\s*{_VALIDITY_LABEL}", re.I)
_VALIDITY_ALONE = re.compile(rf"{_VALIDITY_LABEL}\s*[:：\-–]?\s*$", re.I)
_DATE_ALONE = re.compile(rf"^\s*({_TEXT_DATE})")


def _find_validity_date(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    for idx, line in enumerate(lines):
        match = _VALIDITY_AFTER.search(line)
        if match:
            return match[1]
        match = _VALIDITY_BEFORE.search(line)
        # A date that follows another label's colon ("Date: 19/10/2026 :...") is that label's.
        if match and not line[: match.start()].rstrip().endswith((":", "：")):
            return match[1]
        # Without a colon, a date followed by one is the next label's value in visual order.
        match = _VALIDITY_AFTER_LOOSE.search(line)
        if match:
            return match[1]
        if _VALIDITY_ALONE.search(line):
            following = next((nxt for nxt in lines[idx + 1 :] if nxt), "")
            date_match = _DATE_ALONE.match(following)
            if date_match:
                return date_match[1]
    return None


def _find_grand_total(text: str, currency: str | None) -> ExtractedField | None:
    before_tax: ExtractedField | None = None
    grand_total: ExtractedField | None = None
    for line in text.splitlines():
        if _is_total_row(line):
            clean_line = _PERCENTAGE_PATTERN.sub("", line)
            amounts = re.findall(r"[\d٠-٩۰-۹][\d٠-٩۰-۹.,٬٫]*", clean_line)
            if amounts:
                amount: str | None = None
                for match in re.finditer(r"[\d٠-٩۰-۹][\d٠-٩۰-۹.,٬٫]*", clean_line):
                    candidate_amt = _clean_number(match.group())
                    if not candidate_amt:
                        continue
                    start, end = match.span()
                    before = clean_line[:start].rstrip()
                    after = clean_line[end:].lstrip()
                    if any(
                        m.search(before[-10:]) or m.search(after[:10])
                        for m in (_SAR_MARKER, _EUR_MARKER, _EGP_MARKER, _OTHER_MARKER)
                    ):
                        amount = candidate_amt
                if not amount:
                    amount = _clean_number(amounts[-1])
                if amount:
                    candidate = _money_field("stated_total", amount, currency, 0.9)
                    if _is_before_tax_row(line):
                        before_tax = candidate
                    else:
                        grand_total = candidate
    return before_tax or grand_total


def _has_before_tax_total(text: str) -> bool:
    return any(_is_total_row(line) and _is_before_tax_row(line) for line in text.splitlines())


def _has_currency_conflict(text: str) -> bool:
    codes = {
        code
        for code, pattern in (("EGP", _EGP_MARKER), ("SAR", _SAR_MARKER), ("EUR", _EUR_MARKER))
        if any(_adjacent_to_number(text, *match.span()) for match in pattern.finditer(text))
    }
    other = any(_adjacent_to_number(text, *match.span()) for match in _OTHER_MARKER.finditer(text))
    return len(codes) > 1 or (bool(codes) and other)


def _merge_headers(
    base: ExtractionResult, table: ExtractionResult, invoice_total: ExtractedField | None = None
) -> ExtractionResult:
    header = dict(base.header)
    if table.expected_line_count is not None and "currency" not in table.header:
        header.pop("currency", None)
    header.update(table.header)
    return ExtractionResult(
        "azure_di",
        table.model_version,
        header,
        table.lines,
        table.stated_total or invoice_total,
        table.cost_usd,
        expected_line_count=table.expected_line_count,
    )


def _parse_line_item(idx: int, item_fields: dict[str, Any], currency: str) -> ExtractedLine:
    fields: dict[str, ExtractedField] = {}

    desc = _content_from(item_fields, "Description") or ""
    qty = _content_from(item_fields, "Quantity")
    if qty is not None:
        cleaned = _clean_number(str(qty))
        if cleaned:
            fields["quantity"] = ExtractedField(
                "quantity", cleaned, _conf_from(item_fields, "Quantity") or 0.88, 1, None
            )

    unit = _content_from(item_fields, "Unit")
    if unit:
        fields["pack_unit"] = ExtractedField("pack_unit", str(unit), 0.85, 1, None)

    unit_price = _content_from(item_fields, "UnitPrice")
    if unit_price is not None:
        amount = _clean_number(str(unit_price))
        if amount:
            fields["unit_price"] = ExtractedField(
                "unit_price",
                {"amount": amount, "currency": currency},
                _conf_from(item_fields, "UnitPrice") or 0.88,
                1,
                None,
            )

    return ExtractedLine(
        line_number=idx,
        original_text=str(desc) if desc else f"Line {idx}",
        fields=fields,
    )


def _content(fields: dict[str, Any], name: str) -> str | None:
    field = fields.get(name)
    if field is None:
        return None
    return _get(field, "content")


def _date_evidence(fields: dict[str, Any], name: str) -> object | None:
    field = fields.get(name)
    if field is None:
        return None
    content = _get(field, "content")
    if content:
        return content
    typed_date = _get(field, "value_date")
    return typed_date.isoformat() if isinstance(typed_date, (date, datetime)) else typed_date


def _typed_date(fields: dict[str, Any], name: str) -> date | datetime | None:
    field = fields.get(name)
    value = _get(field, "value_date") if field is not None else None
    return value if isinstance(value, (date, datetime)) else None


def _confidence(fields: dict[str, Any], name: str) -> float | None:
    field = fields.get(name)
    if field is None:
        return None
    return _get(field, "confidence")


def _content_from(item_fields: dict[str, Any], name: str) -> str | None:
    field = item_fields.get(name)
    if field is None:
        return None
    return _get(field, "content")


def _conf_from(item_fields: dict[str, Any], name: str) -> float | None:
    field = item_fields.get(name)
    if field is None:
        return None
    return _get(field, "confidence")


def _make_field(
    name: str,
    value: object,
    fields: dict[str, Any],
    azure_field_name: str,
    *,
    typed_value: object | None = None,
) -> ExtractedField:
    conf = _confidence(fields, azure_field_name)
    return ExtractedField(
        name=name,
        value=value,
        confidence=conf if conf is not None else 0.85,
        source_page=1,
        source_region=None,
        typed_value=typed_value,
    )


def _clean_number(s: str) -> str | None:
    s = _PERCENTAGE_PATTERN.sub("", s)
    s = _SAR_MARKER.sub("", s)
    s = _EUR_MARKER.sub("", s)
    s = re.sub(
        r"ج\s*\.\s*م\.?|جنيه(?:\s+مصري)?|(?<![A-Z])L\.?\s*E\.?(?![A-Z])|\b(?:EGP|USD|GBP|EUR)\b",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"[$£€]", "", s)
    cleaned = re.sub(r"[^\d.,\-٠-٩۰-۹٫٬−﹣]", "", s)
    if not cleaned or cleaned in (".", ",", "٫", "-"):
        return None
    if "٫" in cleaned or "٬" in cleaned:
        try:
            return format(parse_localised_decimal(cleaned), "f")
        except ValueError:
            return None
    if "," in cleaned and "." not in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", "")
    try:
        return format(parse_localised_decimal(cleaned), "f")
    except ValueError:
        return None


def _numeric_cell_amount(text: str) -> str | None:
    text = _PERCENTAGE_PATTERN.sub("", text)
    text = _SAR_MARKER.sub("", text)
    text = _EUR_MARKER.sub("", text)
    cleaned = re.sub(
        r"ج\s*\.\s*م\.?|جنيه(?:\s+مصري)?|(?<![A-Z])L\.?\s*E\.?(?![A-Z])|\b(?:EGP|USD|GBP|EUR)\b|[$£€]",
        "",
        text,
        flags=re.I,
    ).strip()
    if not re.fullmatch(r"[\d٠-٩۰-۹.,٬٫\s−﹣-]+", cleaned):
        return None
    return _clean_number(cleaned)


def _infer_currency(fields: dict[str, Any]) -> str | None:
    return _infer_currency_state(fields)[0]


def _infer_currency_state(fields: dict[str, Any]) -> tuple[str | None, bool]:
    all_content = " ".join(str(_get(field, "content", "") or "") for field in fields.values())
    marker_currency = detect_currency(all_content)
    codes: set[str] = set()
    for field in fields.values():
        marker = detect_currency(str(_get(field, "content", "") or ""))
        if marker:
            codes.add(marker)
    for name in ("InvoiceTotal", "SubTotal", "AmountDue"):
        field = fields.get(name)
        if field is None:
            continue
        cur = _get(field, "currency_code")
        if cur:
            codes.add(str(cur).upper())
        content = _get(field, "content", "") or ""
        for code, marker in (("GBP", "£"), ("USD", "$"), ("EUR", "€")):
            if marker in content or code in content.upper():
                codes.add(code)
    if marker_currency:
        codes.add(marker_currency)
    conflict = len(codes) > 1 or _has_currency_conflict(all_content)
    return (next(iter(codes)) if len(codes) == 1 and not conflict else None, conflict)
