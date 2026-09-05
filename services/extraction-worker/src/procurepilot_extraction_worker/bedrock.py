from __future__ import annotations

import json
from typing import Any

import boto3

from procurepilot_extraction_worker.models import (
    ExtractedField,
    ExtractedLine,
    ExtractionResult,
)
from procurepilot_extraction_worker.providers import ExtractionProviderError
from procurepilot_extraction_worker.settings import WorkerSettings, get_settings

EXTRACTION_PROMPT = """\
You are a commercial document extraction engine. Extract structured data from this supplier \
quotation document.

Return a JSON object with exactly this schema — no markdown fences, no commentary:
{
  "header": {
    "supplier_name": "<string or null>",
    "currency": "<ISO 4217 code>",
    "issue_date": "<YYYY-MM-DD or null>",
    "expiry_date": "<YYYY-MM-DD or null>"
  },
  "lines": [
    {
      "line_number": <int>,
      "original_text": "<the raw line text as it appears in the document>",
      "quantity": "<decimal string>",
      "pack_count": <int or null>,
      "unit_size": "<decimal string or null>",
      "pack_unit": "<string or null>",
      "unit_price": { "amount": "<decimal string>", "currency": "<ISO 4217>" },
      "vat_rate": "<decimal string 0-1 or null>",
      "delivery_fee": { "amount": "<decimal string>", "currency": "<ISO 4217>" } or null,
      "discount": { "amount": "<decimal string>", "currency": "<ISO 4217>" } or null
    }
  ],
  "stated_total": { "amount": "<decimal string>", "currency": "<ISO 4217>" } or null
}

Rules:
- Extract every line item. Do not skip rows.
- All monetary amounts must include an explicit currency.
- If the document states a total (subtotal, grand total, total due), put the final total in \
stated_total.
- Dates in YYYY-MM-DD. If a date is ambiguous, prefer DD/MM/YYYY interpretation.
- pack_count is the number of packs; unit_size is the weight/volume per pack.
- vat_rate as a fraction (e.g. 0.20 for 20%).
- original_text is the verbatim text of the line as printed in the document.
- Return only the JSON object.\
"""

MIME_TO_CONVERSE_FORMAT: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
}


class BedrockExtractionProvider:
    method = "bedrock"

    def __init__(self, settings: WorkerSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self.model_version = self._settings.bedrock_model_id

    def extract(
        self,
        *,
        document_id: str,
        mime_type: str,
        storage_path: str,
        document_bytes: bytes | None = None,
    ) -> ExtractionResult:
        if document_bytes is None:
            raise ExtractionProviderError("document_bytes required for Bedrock extraction")

        doc_format = MIME_TO_CONVERSE_FORMAT.get(mime_type)
        if doc_format is None:
            raise ExtractionProviderError(f"unsupported mime type for Bedrock: {mime_type}")

        session_kwargs: dict[str, str] = {}
        if self._settings.aws_profile:
            session_kwargs["profile_name"] = self._settings.aws_profile
        session = boto3.Session(**session_kwargs)
        client = session.client(
            "bedrock-runtime",
            region_name=self._settings.aws_region,
        )

        if mime_type in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            media_block: dict[str, Any] = {
                "image": {
                    "format": doc_format,
                    "source": {"bytes": document_bytes},
                }
            }
        else:
            media_block = {
                "document": {
                    "name": "quotation",
                    "format": doc_format,
                    "source": {"bytes": document_bytes},
                }
            }

        messages = [
            {
                "role": "user",
                "content": [
                    media_block,
                    {"text": EXTRACTION_PROMPT},
                ],
            }
        ]

        try:
            response = client.converse(
                modelId=self._settings.bedrock_model_id,
                messages=messages,
                inferenceConfig={"maxTokens": 8192},
            )
        except Exception as exc:
            raise ExtractionProviderError(f"Bedrock converse failed: {exc}") from exc

        output = response["output"]["message"]["content"]
        text = ""
        for block in output:
            if "text" in block:
                text += block["text"]

        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        cost_usd = _estimate_cost(input_tokens, output_tokens, self._settings.bedrock_model_id)

        return _parse_response(text, self._settings.bedrock_model_id, cost_usd)


def _estimate_cost(input_tokens: int, output_tokens: int, model_id: str) -> float:
    model = model_id.lower()
    if "haiku" in model:
        return (input_tokens * 0.0008 + output_tokens * 0.004) / 1000
    if "sonnet" in model:
        return (input_tokens * 0.003 + output_tokens * 0.015) / 1000
    return 0.0


def _parse_response(raw: str, model_version: str, cost_usd: float) -> ExtractionResult:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError(f"Bedrock returned invalid JSON: {exc}") from exc

    header_raw = data.get("header", {})
    header: dict[str, ExtractedField] = {}
    for name in ("supplier_name", "currency", "issue_date", "expiry_date"):
        value = header_raw.get(name)
        if value is not None:
            header[name] = ExtractedField(
                name=name,
                value=value,
                confidence=0.92,
                source_page=1,
                source_region=None,
            )

    lines: list[ExtractedLine] = []
    for line_raw in data.get("lines", []):
        fields: dict[str, ExtractedField] = {}
        for name in ("quantity", "pack_count", "unit_size", "pack_unit", "vat_rate"):
            value = line_raw.get(name)
            if value is not None:
                fields[name] = ExtractedField(name, value, 0.90, 1, None)
        for name in ("unit_price", "delivery_fee", "discount"):
            value = line_raw.get(name)
            if value is not None and isinstance(value, dict):
                fields[name] = ExtractedField(name, value, 0.90, 1, None)

        lines.append(
            ExtractedLine(
                line_number=int(line_raw.get("line_number", len(lines) + 1)),
                original_text=str(line_raw.get("original_text", "")),
                fields=fields,
            )
        )

    stated_total: ExtractedField | None = None
    st_raw = data.get("stated_total")
    if isinstance(st_raw, dict) and st_raw.get("amount"):
        stated_total = ExtractedField("stated_total", st_raw, 0.90, 1, None)

    return ExtractionResult(
        method="bedrock",
        model_version=model_version,
        header=header,
        lines=lines,
        stated_total=stated_total,
        cost_usd=cost_usd,
    )
