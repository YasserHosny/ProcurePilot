from __future__ import annotations

import re
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from procurepilot_extraction_worker.models import (
    ExtractedField,
    ExtractedLine,
    ExtractionResult,
)
from procurepilot_extraction_worker.providers import ExtractionProviderError
from procurepilot_extraction_worker.settings import WorkerSettings, get_settings

MODEL_ID = "prebuilt-invoice"


class AzureDocumentIntelligenceProvider:
    method = "azure_di"
    model_version = f"{MODEL_ID}:2024-11-30"

    def __init__(self, settings: WorkerSettings | None = None) -> None:
        self._settings = settings or get_settings()

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
        if not endpoint or not key:
            raise ExtractionProviderError("AZURE_DI_ENDPOINT and AZURE_DI_KEY are required")

        client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key),
        )

        try:
            poller = client.begin_analyze_document(
                MODEL_ID,
                AnalyzeDocumentRequest(bytes_source=document_bytes),
            )
            result = poller.result()
        except Exception as exc:
            raise ExtractionProviderError(f"Azure DI analysis failed: {exc}") from exc

        return _parse_invoice_result(result, self.model_version)


def _parse_invoice_result(result: Any, model_version: str) -> ExtractionResult:
    header: dict[str, ExtractedField] = {}
    lines: list[ExtractedLine] = []
    stated_total: ExtractedField | None = None

    documents = getattr(result, "documents", None) or []
    if not documents:
        return _fallback_from_tables(result, model_version)

    doc = documents[0]
    fields = doc.fields or {}

    vendor = _content(fields, "VendorName")
    if vendor:
        header["supplier_name"] = _make_field("supplier_name", vendor, fields, "VendorName")

    currency = _infer_currency(fields) or "GBP"
    header["currency"] = ExtractedField("currency", currency, 0.90, 1, None)

    invoice_date = _content(fields, "InvoiceDate")
    if invoice_date:
        header["issue_date"] = _make_field(
            "issue_date", _normalise_date(invoice_date), fields, "InvoiceDate"
        )

    due_date = _content(fields, "DueDate")
    if due_date:
        header["expiry_date"] = _make_field(
            "expiry_date", _normalise_date(due_date), fields, "DueDate"
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
    if items_field:
        item_list = getattr(items_field, "value_array", None) or []
        for idx, item in enumerate(item_list, start=1):
            item_fields = getattr(item, "value_object", None) or {}
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


def _fallback_from_tables(result: Any, model_version: str) -> ExtractionResult:
    tables = getattr(result, "tables", None) or []
    lines: list[ExtractedLine] = []
    for table in tables:
        cells = table.cells or []
        headers_row = [c for c in cells if c.row_index == 0]
        header_names = [
            c.content.strip().lower()
            for c in sorted(headers_row, key=lambda c: c.column_index)
        ]
        for row_idx in range(1, table.row_count):
            row_cells = sorted(
                [c for c in cells if c.row_index == row_idx],
                key=lambda c: c.column_index,
            )
            row_data: dict[str, str] = {}
            for cell in row_cells:
                if cell.column_index < len(header_names):
                    row_data[header_names[cell.column_index]] = cell.content
            if row_data:
                ef: dict[str, ExtractedField] = {}
                qty = row_data.get("quantity") or row_data.get("qty")
                if qty:
                    ef["quantity"] = ExtractedField("quantity", qty, 0.80, 1, None)
                price = (
                    row_data.get("unit price") or row_data.get("price") or row_data.get("rate")
                )
                if price:
                    amount = _clean_number(price)
                    if amount:
                        ef["unit_price"] = ExtractedField(
                            "unit_price", {"amount": amount, "currency": "USD"}, 0.80, 1, None
                        )
                desc = (
                    row_data.get("description")
                    or row_data.get("item")
                    or row_data.get("product")
                    or " ".join(row_data.values())
                )
                lines.append(
                    ExtractedLine(
                        line_number=row_idx,
                        original_text=desc or f"Table row {row_idx}",
                        fields=ef,
                    )
                )
    return ExtractionResult(
        method="azure_di",
        model_version=model_version,
        header={},
        lines=lines,
        stated_total=None,
        cost_usd=0.0,
        warnings=("no structured invoice detected; extracted from tables",),
    )


def _parse_line_item(
    idx: int, item_fields: dict[str, Any], currency: str
) -> ExtractedLine:
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
    return getattr(field, "content", None)


def _confidence(fields: dict[str, Any], name: str) -> float | None:
    field = fields.get(name)
    if field is None:
        return None
    return getattr(field, "confidence", None)


def _content_from(item_fields: dict[str, Any], name: str) -> str | None:
    field = item_fields.get(name)
    if field is None:
        return None
    return getattr(field, "content", None)


def _conf_from(item_fields: dict[str, Any], name: str) -> float | None:
    field = item_fields.get(name)
    if field is None:
        return None
    return getattr(field, "confidence", None)


def _make_field(
    name: str, value: Any, fields: dict[str, Any], azure_field_name: str
) -> ExtractedField:
    conf = _confidence(fields, azure_field_name)
    return ExtractedField(
        name=name,
        value=value,
        confidence=conf if conf is not None else 0.85,
        source_page=1,
        source_region=None,
    )


def _clean_number(s: str) -> str | None:
    cleaned = re.sub(r"[^\d.,\-]", "", s)
    if not cleaned or cleaned in (".", ",", "-"):
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    return cleaned


def _normalise_date(value: str) -> str:
    if re.match(r"\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return value


def _infer_currency(fields: dict[str, Any]) -> str | None:
    for name in ("InvoiceTotal", "SubTotal", "AmountDue"):
        field = fields.get(name)
        if field is None:
            continue
        cur = getattr(field, "currency_code", None)
        if cur:
            return str(cur)
        content = getattr(field, "content", "") or ""
        if "£" in content or "GBP" in content:
            return "GBP"
        if "$" in content or "USD" in content:
            return "USD"
        if "€" in content or "EUR" in content:
            return "EUR"
    return None
