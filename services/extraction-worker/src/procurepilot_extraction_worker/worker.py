from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID

import psycopg
from procurepilot_logging import get_trace_id, new_trace_id, set_trace_id

from procurepilot_extraction_worker.azure_di import AzureDocumentIntelligenceProvider
from procurepilot_extraction_worker.bedrock import BedrockExtractionProvider
from procurepilot_extraction_worker.models import ExtractedField, ExtractedLine, ExtractionResult
from procurepilot_extraction_worker.settings import WorkerSettings, get_settings
from procurepilot_extraction_worker.structured_parse import is_structured_mime_type
from procurepilot_extraction_worker.validation import low_confidence_fields, validate_arithmetic

logger = logging.getLogger(__name__)


def process_extraction_job(payload: dict[str, str]) -> None:
    set_trace_id(new_trace_id())
    settings = get_settings()
    job_id = UUID(payload["job_id"])
    tenant_id = UUID(payload["tenant_id"])
    quotation_id = UUID(payload["quotation_id"])
    document_id = UUID(payload["document_id"])
    logger.info(
        "extraction job started",
        extra={"job_id": str(job_id), "document_id": str(document_id)},
    )
    # prepare_threshold=None: DATABASE_URL runs through Supabase's transaction-mode pooler,
    # which hands out reused backend sessions. psycopg3's default server-side prepared
    # statements collide across connections on that shared session (DuplicatePreparedStatement:
    # "_pg3_0" already exists) the moment a second job runs.
    with psycopg.connect(settings.database_url, prepare_threshold=None) as conn:
        document = _document(conn, tenant_id, document_id)
        _mark_running(conn, job_id)
        try:
            result = _extract(settings, document_id=document_id, document=document)
            arithmetic = validate_arithmetic(result)
            _persist_result(conn, tenant_id, quotation_id, result, arithmetic.status)
            review_reason = _review_reason(result, arithmetic.status, settings.confidence_threshold)
            if review_reason is not None:
                _upsert_review_task(conn, tenant_id, quotation_id, review_reason)
                quotation_status = "in_review"
            else:
                quotation_status = "extracted"
            _update_quotation_status(
                conn,
                quotation_id,
                quotation_status,
                arithmetic.status,
                result,
            )
            _mark_succeeded(conn, job_id, result.method)
            logger.info(
                "extraction job succeeded",
                extra={
                    "job_id": str(job_id),
                    "method": result.method,
                    "lines": len(result.lines),
                    "arithmetic": arithmetic.status,
                    "quotation_status": quotation_status,
                },
            )
        except Exception as exc:
            conn.rollback()
            _mark_failed(conn, job_id, {"code": "extraction_failed", "message": str(exc)})
            _refuse_quotation(conn, quotation_id)
            # The `with` block below commits on a clean exit but rolls back on one exiting
            # via an exception — which the `raise` below does. Without this commit, the
            # failure bookkeeping above is silently undone and the job/quotation are left
            # stuck at "queued"/"extracting" forever instead of recording as failed/refused.
            conn.commit()
            logger.exception(
                "extraction job failed",
                extra={"job_id": str(job_id), "document_id": str(document_id)},
            )
            raise


def _extract(
    settings: WorkerSettings,
    *,
    document_id: UUID,
    document: dict[str, object],
) -> ExtractionResult:
    mime_type = str(document["mime_type"])
    storage_path = str(document["storage_path"])
    bucket = str(document["storage_bucket"])
    if is_structured_mime_type(mime_type):
        from procurepilot_extraction_worker.structured_parse import parse_structured_content

        logger.info("using structured parser", extra={"mime_type": mime_type})
        content = _download_storage_object(settings, bucket=bucket, path=storage_path)
        return parse_structured_content(content, mime_type=mime_type)
    doc_bytes = _download_storage_object(settings, bucket=bucket, path=storage_path)
    common = dict(
        document_id=str(document_id),
        mime_type=mime_type,
        storage_path=storage_path,
        document_bytes=doc_bytes,
    )
    if settings.provider_mode == "azure_di":
        logger.info("using azure_di provider")
        return AzureDocumentIntelligenceProvider(settings).extract(**common)
    logger.info("using bedrock provider")
    try:
        return BedrockExtractionProvider(settings).extract(**common)
    except Exception:
        logger.warning("bedrock failed, falling back to azure_di", exc_info=True)
        return AzureDocumentIntelligenceProvider(settings).extract(**common)


def _persist_result(
    conn: psycopg.Connection,
    tenant_id: UUID,
    quotation_id: UUID,
    result: ExtractionResult,
    arithmetic_status: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "delete from field_extraction where tenant_id = %s and quotation_id = %s",
            (tenant_id, quotation_id),
        )
        cur.execute(
            "delete from quotation_line where tenant_id = %s and quotation_id = %s",
            (tenant_id, quotation_id),
        )
        for line in result.lines:
            pack_count = _safe_numeric(_field_value(line, "pack_count"))
            unit_size = _safe_numeric(_field_value(line, "unit_size"))
            if (pack_count is None) != (unit_size is None):
                pack_count = None
                unit_size = None
            cur.execute(
                """
                insert into quotation_line (
                  tenant_id, quotation_id, line_number, original_text, quantity, pack_count,
                  unit_size, pack_unit, unit_price_amount, unit_price_currency, vat_rate,
                  delivery_fee_amount, delivery_fee_currency, discount_amount, discount_currency
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                returning id
                """,
                (
                    tenant_id,
                    quotation_id,
                    line.line_number,
                    line.original_text,
                    _safe_numeric(_field_value(line, "quantity")),
                    pack_count,
                    unit_size,
                    _normalise_pack_unit(_field_value(line, "pack_unit")),
                    _money_amount(line, "unit_price"),
                    _money_currency(line, "unit_price"),
                    _safe_numeric(_field_value(line, "vat_rate")),
                    _money_amount(line, "delivery_fee"),
                    _money_currency(line, "delivery_fee"),
                    _money_amount(line, "discount"),
                    _money_currency(line, "discount"),
                ),
            )
            line_id = cur.fetchone()[0]
            for field in line.fields.values():
                _insert_field(
                    cur,
                    tenant_id,
                    quotation_id,
                    "quotation_line",
                    line_id,
                    field,
                    result,
                )
        for field in result.header.values():
            _insert_field(cur, tenant_id, quotation_id, "quotation", quotation_id, field, result)
        if result.stated_total is not None:
            _insert_field(
                cur,
                tenant_id,
                quotation_id,
                "quotation",
                quotation_id,
                result.stated_total,
                result,
            )
        if arithmetic_status == "mismatch":
            _upsert_review_task(conn, tenant_id, quotation_id, "arithmetic_mismatch")


def _insert_field(
    cur: psycopg.Cursor,
    tenant_id: UUID,
    quotation_id: UUID,
    entity_type: str,
    entity_id: UUID,
    field: ExtractedField,
    result: ExtractionResult,
) -> None:
    cur.execute(
        """
        insert into field_extraction (
          tenant_id, quotation_id, entity_type, entity_id, field_name, extracted_value,
          confidence, source_page, source_region, extraction_method, model_version
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (tenant_id, entity_type, entity_id, field_name) do update set
          extracted_value = excluded.extracted_value,
          confidence = excluded.confidence,
          source_page = excluded.source_page,
          source_region = excluded.source_region,
          extraction_method = excluded.extraction_method,
          model_version = excluded.model_version
        """,
        (
            tenant_id,
            quotation_id,
            entity_type,
            entity_id,
            field.name,
            psycopg.types.json.Jsonb(field.value),
            f"{field.confidence:.4f}",
            field.source_page,
            (
                psycopg.types.json.Jsonb(field.source_region)
                if field.source_region is not None
                else None
            ),
            result.method,
            result.model_version,
        ),
    )


def _update_quotation_status(
    conn: psycopg.Connection,
    quotation_id: UUID,
    status: str,
    arithmetic_status: str,
    result: ExtractionResult,
) -> None:
    stated = result.stated_total.value if result.stated_total is not None else None
    amount = stated.get("amount") if isinstance(stated, dict) else None
    currency = stated.get("currency") if isinstance(stated, dict) else None
    header = result.header
    with conn.cursor() as cur:
        cur.execute(
            """
            update quotation
            set status = %s, currency = coalesce(%s, currency), issue_date = %s,
                expiry_date = %s, stated_total_amount = %s, stated_total_currency = %s,
                arithmetic_status = %s
            where id = %s
            """,
            (
                status,
                _header_value(header, "currency"),
                _header_value(header, "issue_date"),
                _header_value(header, "expiry_date"),
                amount,
                currency,
                arithmetic_status,
                quotation_id,
            ),
        )


def _review_reason(
    result: ExtractionResult,
    arithmetic_status: str,
    threshold: float,
) -> str | None:
    if arithmetic_status == "mismatch":
        return "arithmetic_mismatch"
    if low_confidence_fields(result, threshold):
        return "low_confidence"
    return None


def _upsert_review_task(
    conn: psycopg.Connection,
    tenant_id: UUID,
    quotation_id: UUID,
    reason: str,
) -> None:
    priority = "high" if reason == "arithmetic_mismatch" else "normal"
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into review_task (tenant_id, quotation_id, status, priority, reason)
            values (%s,%s,'open',%s,%s)
            on conflict (tenant_id, quotation_id) where status in ('open','in_progress')
            do update set priority = excluded.priority, reason = excluded.reason
            """,
            (tenant_id, quotation_id, priority, reason),
        )


def _document(conn: psycopg.Connection, tenant_id: UUID, document_id: UUID) -> dict[str, object]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            select id,mime_type,storage_bucket,storage_path
            from document
            where tenant_id = %s and id = %s
            """,
            (tenant_id, document_id),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("document not found for extraction job")
    return dict(row)


def _download_storage_object(settings: WorkerSettings, *, bucket: str, path: str) -> bytes:
    if not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for structured extraction")
    encoded_path = quote(path, safe="/")
    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{encoded_path}"
    request = Request(
        url,
        headers={
            "apikey": settings.supabase_service_role_key,
            "authorization": f"Bearer {settings.supabase_service_role_key}",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except URLError as exc:
        raise RuntimeError("could not download structured quotation document") from exc


def _mark_running(conn: psycopg.Connection, job_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "update extraction_job set status = 'running', started_at = %s where id = %s",
            (datetime.now(UTC), job_id),
        )


def _mark_succeeded(conn: psycopg.Connection, job_id: UUID, method: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update extraction_job
            set status = 'succeeded', attempted_provider = %s, completed_at = %s
            where id = %s
            """,
            (method, datetime.now(UTC), job_id),
        )


def _mark_failed(conn: psycopg.Connection, job_id: UUID, error: dict[str, object]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update extraction_job
            set status = 'failed', error = %s, completed_at = %s
            where id = %s
            """,
            (psycopg.types.json.Jsonb(error), datetime.now(UTC), job_id),
        )


def _refuse_quotation(conn: psycopg.Connection, quotation_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("update quotation set status = 'refused' where id = %s", (quotation_id,))


_UNIT_ALIASES: dict[str, str] = {
    "box": "each",
    "boxes": "each",
    "bag": "each",
    "bags": "each",
    "bottle": "each",
    "bottles": "each",
    "can": "each",
    "cans": "each",
    "pack": "each",
    "packs": "each",
    "packet": "each",
    "piece": "each",
    "pieces": "each",
    "pcs": "each",
    "unit": "each",
    "units": "each",
    "ea": "each",
    "each": "each",
    "kg": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "kgs": "kilogram",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "l": "litre",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "ml": "millilitre",
    "millilitre": "millilitre",
    "millilitres": "millilitre",
    "milliliter": "millilitre",
}


def _normalise_pack_unit(raw: object) -> str | None:
    if raw is None:
        return None
    return _UNIT_ALIASES.get(str(raw).strip().lower())


def _safe_numeric(raw: object) -> object | None:
    if raw is None:
        return None
    try:
        return float(str(raw))
    except (ValueError, TypeError):
        return None


def _field_value(line: ExtractedLine, name: str) -> object | None:
    field = line.fields.get(name)
    return field.value if field is not None else None


def _money_amount(line: ExtractedLine, name: str) -> object | None:
    value = _field_value(line, name)
    return value.get("amount") if isinstance(value, dict) else None


def _money_currency(line: ExtractedLine, name: str) -> str | None:
    value = _field_value(line, name)
    return str(value["currency"]) if isinstance(value, dict) and value.get("currency") else None


def _header_value(header: dict[str, ExtractedField], name: str) -> object | None:
    field = header.get(name)
    return field.value if field is not None else None
