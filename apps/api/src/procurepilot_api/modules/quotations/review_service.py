from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as calendar_date
from decimal import Decimal, InvalidOperation
from typing import NoReturn
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import ValidationError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.review_gate import blocking_low_confidence_fields
from procurepilot_api.modules.quotations.schemas import (
    FieldCorrection,
    QuotationDetail,
    QuotationReviewPatch,
)
from procurepilot_api.modules.quotations.service import (
    FIELD_COLUMNS,
    QuotationService,
    _one_row,
    _rows,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

ARITHMETIC_TOLERANCE = Decimal("0.01")


class QuotationReviewService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def apply_review_patch(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
        patch: QuotationReviewPatch,
    ) -> QuotationDetail:
        client = authenticated_client(self._settings, bearer_token)
        quotation = _one_row(
            client.table("quotation")
            .select("id,status,supplier_id,currency,reviewer_notes,tenant_id,prices_include_vat")
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
            .data,
            resource="quotation",
        )
        if quotation["status"] not in {"extracted", "in_review"}:
            raise ConflictError(details={"reason": "quotation_not_editable"})

        updates: dict[str, object] = {"status": "in_review"}
        if "supplier_id" in patch.model_fields_set:
            if patch.supplier_id is not None:
                _one_row(
                    client.table("supplier")
                    .select("id")
                    .eq("id", str(patch.supplier_id))
                    .limit(2)
                    .execute()
                    .data,
                    resource="supplier",
                )
            updates["supplier_id"] = str(patch.supplier_id) if patch.supplier_id else None
        if "currency" in patch.model_fields_set:
            updates["currency"] = patch.currency

        if "prices_include_vat" in patch.model_fields_set:
            updates["prices_include_vat"] = patch.prices_include_vat

        if "reviewer_notes" in patch.model_fields_set:
            updates["reviewer_notes"] = patch.reviewer_notes
        quotation_tenant_id = quotation.get("tenant_id")
        if patch.add_lines and quotation_tenant_id is None:
            raise ServiceUnavailableError(details={"reason": "quotation_not_found"})

        # Resolve and validate every correction before the first mutation. PostgREST does
        # not provide a transaction spanning these requests, so validation belongs here.
        live_lines = _rows(
            client.table("quotation_line")
            .select("*")
            .eq("quotation_id", str(quotation_id))
            .execute()
            .data
        )
        lines_by_id = {str(line["id"]): dict(line) for line in live_lines}
        line_updates: dict[str, dict[str, object]] = {}
        removed_lines: list[dict[str, object]] = []
        for line_id in dict.fromkeys(patch.remove_line_ids):
            line = _one_row(
                [line for line in live_lines if str(line["id"]) == str(line_id)],
                resource="quotation_line",
            )
            removed_lines.append(line)

        correction_fields: list[tuple[FieldCorrection, dict[str, object]]] = []
        for correction in patch.corrections:
            field = _one_row(
                client.table("field_extraction")
                .select(FIELD_COLUMNS)
                .eq("id", str(correction.field_extraction_id))
                .eq("quotation_id", str(quotation_id))
                .limit(2)
                .execute()
                .data,
                resource="field_extraction",
            )
            field_name = field.get("field_name")
            if field.get("entity_type") == "quotation_line":
                line = _one_row(
                    [line for line in live_lines if str(line["id"]) == str(field["entity_id"])],
                    resource="quotation_line",
                )
                if field.get("corrected_by") is None:
                    _validate_line_correction(client, str(field_name), correction.corrected_value)
                    payload = _line_correction_payload(str(field_name), correction.corrected_value)
                    lines_by_id[str(line["id"])].update(payload)
                    line_updates.setdefault(str(line["id"]), {}).update(payload)
            if field.get("entity_type") == "quotation" and field_name in {
                "prices_include_vat",
                "vat_rate",
            }:
                try:
                    QuotationReviewPatch(**{str(field_name): correction.corrected_value})
                except ValidationError as exc:
                    raise ConflictError(details={"reason": "invalid_vat_correction"}) from exc
            if (
                field.get("corrected_by") is None
                and field.get("entity_type") == "quotation"
                and field_name in {"stated_total", "currency"}
            ):
                _validate_header_correction(client, str(field_name), correction.corrected_value)
            is_date_field = field_name in {"issue_date", "expiry_date"}
            if (
                field.get("corrected_by") is None
                and is_date_field
                and not _is_iso_date(correction.corrected_value)
            ):
                raise ConflictError(details={"reason": "invalid_date_correction"})
            correction_fields.append((correction, field))

        for line in lines_by_id.values():
            if (line.get("pack_count") is None) != (line.get("unit_size") is None):
                raise ConflictError(details={"reason": "invalid_pack_correction"})

        try:
            client.table("quotation").update(updates).eq("id", str(quotation_id)).execute()
            for correction, field in correction_fields:
                if field.get("corrected_by") is not None:
                    continue
                client.table("field_extraction").update(
                    {
                        "corrected_value": correction.corrected_value,
                        "corrected_by": str(member.membership_id),
                        "corrected_at": datetime.now(UTC).isoformat(),
                    }
                ).eq("id", str(correction.field_extraction_id)).execute()
                if field.get("entity_type") != "quotation_line":
                    _apply_correction_to_canonical_row(client, field, correction.corrected_value)
            # Pack count and size share a database constraint; apply their corrections
            # together so previously absent packs can be supplied in one review patch.
            for line_id, payload in line_updates.items():
                if payload:
                    client.table("quotation_line").update(payload).eq("id", line_id).eq(
                        "quotation_id", str(quotation_id)
                    ).execute()

            for line in removed_lines:
                line = _one_row(
                    client.table("quotation_line")
                    .delete()
                    .eq("id", str(line["id"]))
                    .eq("quotation_id", str(quotation_id))
                    .execute()
                    .data,
                    resource="quotation_line",
                )
                self._record(
                    bearer_token=bearer_token,
                    member=member,
                    action="quotation.line_removed",
                    target={
                        "quotation_id": str(quotation_id),
                        "line_id": str(line["id"]),
                        "line_number": line["line_number"],
                        "original_text": line["original_text"],
                        "quantity": str(line["quantity"])
                        if line.get("quantity") is not None
                        else None,
                        "unit_price": {
                            "amount": str(line["unit_price_amount"]),
                            "currency": line["unit_price_currency"],
                        }
                        if line.get("unit_price_amount") is not None
                        else None,
                    },
                )

            if patch.add_lines:
                existing_lines = (
                    client.table("quotation_line")
                    .select("line_number")
                    .eq("quotation_id", str(quotation_id))
                    .order("line_number", desc=True)
                    .limit(1)
                    .execute()
                    .data
                )
                next_number = (existing_lines[0]["line_number"] + 1) if existing_lines else 1

                for new_line in patch.add_lines:
                    row_data: dict[str, object] = {
                        "tenant_id": quotation_tenant_id,
                        "quotation_id": str(quotation_id),
                        "line_number": next_number,
                        "original_text": new_line.original_text,
                    }
                    if new_line.quantity is not None:
                        row_data["quantity"] = new_line.quantity
                    if (
                        new_line.unit_price_amount is not None
                        and new_line.unit_price_currency is not None
                    ):
                        row_data["unit_price_amount"] = new_line.unit_price_amount
                        row_data["unit_price_currency"] = new_line.unit_price_currency
                    client.table("quotation_line").insert(row_data).execute()
                    next_number += 1

            if "vat_rate" in patch.model_fields_set:
                _apply_document_vat_rate(client, quotation_id, patch.vat_rate)
            _recompute_arithmetic_status(client, quotation_id)
            _sync_review_task_after_patch(
                client,
                member.tenant_id,
                quotation_id,
                self._settings.extraction_confidence_threshold,
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="quotation.reviewed",
            target={
                "quotation_id": str(quotation_id),
                "corrections_count": len(patch.corrections),
                "added_lines_count": len(patch.add_lines),
                "removed_lines_count": len(patch.remove_line_ids),
                "supplier_changed": (
                    "supplier_id" in patch.model_fields_set
                    and str(quotation.get("supplier_id") or "") != str(patch.supplier_id or "")
                ),
                "currency_changed": (
                    "currency" in patch.model_fields_set
                    and quotation.get("currency") != patch.currency
                ),
                "vat_basis_changed": (
                    bool({"prices_include_vat", "vat_rate"} & patch.model_fields_set)
                    or any(
                        field.get("entity_type") == "quotation"
                        and field.get("field_name") in {"prices_include_vat", "vat_rate"}
                        and field.get("corrected_by") is None
                        for _, field in correction_fields
                    )
                ),
                "notes_changed": (
                    "reviewer_notes" in patch.model_fields_set
                    and (quotation.get("reviewer_notes") or "") != (patch.reviewer_notes or "")
                ),
            },
        )
        return QuotationService(self._settings).get_quotation(
            bearer_token=bearer_token, quotation_id=quotation_id
        )

    def refuse_quotation(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
        reason: str | None,
    ) -> dict[str, object]:
        client = authenticated_client(self._settings, bearer_token)
        quotation = _one_row(
            client.table("quotation")
            .select("id,status")
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
            .data,
            resource="quotation",
        )
        if quotation["status"] not in {"extracted", "in_review"}:
            raise ConflictError(details={"reason": "quotation_not_refusable"})

        try:
            row = _one_row(
                client.table("quotation")
                .update(
                    {
                        "status": "refused",
                        "reviewed_by": str(member.membership_id),
                        "reviewed_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
            client.table("review_task").update(
                {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
            ).eq("quotation_id", str(quotation_id)).in_("status", ["open", "in_progress"]).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="quotation.refused",
                target={"quotation_id": str(quotation_id)},
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )
        from procurepilot_api.modules.ingestion.guardrail_jobs import enqueue_guardrail_evaluation

        enqueue_guardrail_evaluation(
            self._settings, tenant_id=member.tenant_id, quotation_id=quotation_id
        )
        return row

    def _record(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        action: str,
        target: dict[str, object],
    ) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                target=target,
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )


def _apply_correction_to_canonical_row(
    client: object, field: dict[str, object], corrected_value: object
) -> None:
    """Mirror a field_extraction correction onto the row matching/costing actually reads.

    quotation_line's own comment describes it as "as extracted, plus whatever a reviewer
    corrected" — the correction endpoint only ever wrote the overlay in field_extraction,
    never the quotation_line or quotation columns themselves, so a reviewer's fix silently
    never reached arithmetic validation, matching, or landed cost.
    """
    entity_type = field.get("entity_type")
    entity_id = str(field["entity_id"])
    field_name = field.get("field_name")
    if entity_type == "quotation_line":
        payload = _line_correction_payload(str(field_name), corrected_value)
        if payload:
            client.table("quotation_line").update(payload).eq("id", entity_id).execute()
    elif entity_type == "quotation":
        if field_name == "prices_include_vat" and isinstance(corrected_value, bool):
            client.table("quotation").update({field_name: corrected_value}).eq(
                "id", entity_id
            ).execute()
        elif field_name == "vat_rate":
            _apply_document_vat_rate(client, UUID(entity_id), Decimal(str(corrected_value)))
        elif field_name == "currency" and isinstance(corrected_value, str):
            client.table("quotation").update({field_name: corrected_value}).eq(
                "id", entity_id
            ).execute()
        elif field_name in {"issue_date", "expiry_date"} and isinstance(corrected_value, str):
            try:
                canonical_date = calendar_date.fromisoformat(corrected_value).isoformat()
            except ValueError:
                return  # Raw evidence remains in field_extraction; never reaches a date column.
            client.table("quotation").update({field_name: canonical_date}).eq(
                "id", entity_id
            ).execute()
        elif field_name == "stated_total" and isinstance(corrected_value, dict):
            amount = corrected_value.get("amount")
            currency = corrected_value.get("currency")
            if amount is not None and currency is not None:
                client.table("quotation").update(
                    {"stated_total_amount": amount, "stated_total_currency": currency}
                ).eq("id", entity_id).execute()


def _recompute_arithmetic_status(client: object, quotation_id: UUID) -> None:
    quote = _one_row(
        client.table("quotation")
        .select("id,stated_total_amount,arithmetic_status,prices_include_vat")
        .eq("id", str(quotation_id))
        .limit(2)
        .execute()
        .data,
        resource="quotation",
    )
    stated_amount = quote.get("stated_total_amount")
    if stated_amount is None:
        return
    lines = _rows(
        client.table("quotation_line")
        .select("quantity,unit_price_amount,discount_amount,delivery_fee_amount,vat_rate")
        .eq("quotation_id", str(quotation_id))
        .execute()
        .data
    )
    subtotal = Decimal("0")
    has_line_total = False
    has_any_vat = False
    for line in lines:
        if line.get("quantity") is None or line.get("unit_price_amount") is None:
            continue
        has_line_total = True
        quantity = Decimal(str(line["quantity"]))
        unit_price = Decimal(str(line["unit_price_amount"]))
        discount = Decimal(str(line["discount_amount"] or "0"))
        delivery_fee = Decimal(str(line["delivery_fee_amount"] or "0"))
        line_net = quantity * unit_price - discount + delivery_fee
        raw_vat = line.get("vat_rate")
        if raw_vat is not None:
            has_any_vat = True
            vat_rate = Decimal(str(raw_vat))
        else:
            vat_rate = Decimal("0")
        subtotal += line_net if quote.get("prices_include_vat") else line_net * (1 + vat_rate)
    if not has_line_total:
        return
    stated = Decimal(str(stated_amount))
    if abs(subtotal - stated) <= ARITHMETIC_TOLERANCE:
        status = "reconciled"
    elif (
        not quote.get("prices_include_vat")
        and not has_any_vat
        and subtotal > 0
        and stated > subtotal
    ):
        inferred_pct = round(float((stated - subtotal) / subtotal) * 100)
        if 0 < inferred_pct <= 30:
            recomputed = subtotal * (1 + Decimal(str(inferred_pct)) / 100)
            if abs(recomputed - stated) <= ARITHMETIC_TOLERANCE:
                status = "reconciled"
            else:
                status = "mismatch"
        else:
            status = "mismatch"
    else:
        status = "mismatch"
    if status != quote.get("arithmetic_status"):
        client.table("quotation").update({"arithmetic_status": status}).eq(
            "id", str(quotation_id)
        ).execute()


def _sync_review_task_after_patch(
    client: object,
    tenant_id: UUID,
    quotation_id: UUID,
    confidence_threshold: float,
) -> None:
    blocker = _current_review_blocker(client, quotation_id, confidence_threshold)
    open_task_query = (
        client.table("review_task")
        .select("id")
        .eq("quotation_id", str(quotation_id))
        .in_("status", ["open", "in_progress"])
    )
    open_tasks = _rows(open_task_query.execute().data)

    # A patch always leaves the quotation in_review; only authorise/refuse closes its task.
    reason, priority = blocker or ("ready_to_authorise", "low")
    payload: dict[str, object] = {
        "reason": reason,
        "priority": priority,
        "status": "open",
        "resolved_at": None,
    }
    if open_tasks:
        client.table("review_task").update(payload).eq("quotation_id", str(quotation_id)).in_(
            "status", ["open", "in_progress"]
        ).execute()
        return

    client.table("review_task").insert(
        {
            "tenant_id": str(tenant_id),
            "quotation_id": str(quotation_id),
            **payload,
        }
    ).execute()


def _current_review_blocker(
    client: object,
    quotation_id: UUID,
    confidence_threshold: float,
) -> tuple[str, str] | None:
    quote = _one_row(
        client.table("quotation")
        .select("id,supplier_id,currency,arithmetic_status,issue_date,expiry_date")
        .eq("id", str(quotation_id))
        .limit(2)
        .execute()
        .data,
        resource="quotation",
    )
    if quote.get("arithmetic_status") == "mismatch":
        return ("arithmetic_mismatch", "high")
    if quote.get("currency") is None:
        return ("currency_unresolved", "normal")

    date_evidence = (
        client.table("field_extraction")
        .select("field_name,extracted_value")
        .eq("quotation_id", str(quotation_id))
        .eq("entity_type", "quotation")
        .in_("field_name", ["issue_date", "expiry_date"])
        .is_("corrected_by", "null")
        .execute()
        .data
    )
    if any(
        row.get("extracted_value") is not None and quote.get(row.get("field_name")) is None
        for row in _rows(date_evidence)
    ):
        return ("date_unparsed", "normal")

    low_confidence = blocking_low_confidence_fields(
        client, quotation_id, confidence_threshold, supplier_id=quote.get("supplier_id")
    )
    if low_confidence:
        return ("low_confidence", "normal")
    if quote.get("supplier_id") is None:
        return ("no_supplier_match", "normal")
    return None


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return calendar_date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def get_quotation_review_service() -> QuotationReviewService:
    return QuotationReviewService()


def _apply_document_vat_rate(client: object, quotation_id: UUID, rate: Decimal) -> None:
    own_rates = _rows(
        client.table("field_extraction")
        .select("entity_id")
        .eq("quotation_id", str(quotation_id))
        .eq("entity_type", "quotation_line")
        .eq("field_name", "vat_rate")
        .execute()
        .data
    )
    own_ids = {str(field["entity_id"]) for field in own_rates}
    lines = _rows(
        client.table("quotation_line")
        .select("id")
        .eq("quotation_id", str(quotation_id))
        .execute()
        .data
    )
    for line in lines:
        if str(line["id"]) not in own_ids:
            client.table("quotation_line").update({"vat_rate": format(rate, "f")}).eq(
                "id", str(line["id"])
            ).eq("quotation_id", str(quotation_id)).execute()


def _line_correction_payload(name: str, value: object) -> dict[str, object]:
    if name in {"unit_price", "delivery_fee", "discount"} and isinstance(value, dict):
        return {f"{name}_amount": value["amount"], f"{name}_currency": value["currency"]}
    if name in {"description", "original_text"}:
        return {"original_text": value}
    if name == "pack_count":
        return {name: int(Decimal(str(value)))}
    if name in {"quantity", "unit_size", "pack_unit", "vat_rate"}:
        return {name: value}
    # Azure also emits line_total and unparsed pack_text. Neither has a canonical
    # column; retain their review overlay without guessing a price or pack definition.
    return {}


def _check_number(raw: object, *, scale: int, precision: int, reason: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise ConflictError(details={"reason": reason})
    try:
        result = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ConflictError(details={"reason": reason}) from exc
    if not result.is_finite():
        raise ConflictError(details={"reason": reason})
    if abs(result) >= Decimal(10) ** (precision - scale):
        raise ConflictError(details={"reason": reason})
    if result != result.quantize(Decimal(10) ** -scale):
        raise ConflictError(details={"reason": reason})
    return result


def _check_reference(client: object, table: str, code: object, *, reason: str) -> None:
    if not isinstance(code, str) or not _rows(
        client.table(table).select("code").eq("code", code).limit(1).execute().data
    ):
        raise ConflictError(details={"reason": reason})


def _validate_money(client: object, value: object, *, reason: str) -> None:
    if not isinstance(value, dict) or set(value) != {"amount", "currency"}:
        raise ConflictError(details={"reason": reason})
    _check_number(value["amount"], scale=4, precision=18, reason=reason)
    _check_reference(client, "supported_currency", value["currency"], reason=reason)


def _validate_header_correction(client: object, name: str, value: object) -> None:
    reason = f"invalid_{name}_correction"
    if name == "stated_total":
        _validate_money(client, value, reason=reason)
    elif name == "currency":
        _check_reference(client, "supported_currency", value, reason=reason)
    else:
        raise ConflictError(details={"reason": reason})


def _validate_line_correction(client: object, name: str, value: object) -> None:
    reason = f"invalid_{name}_correction"

    def reject() -> NoReturn:
        raise ConflictError(details={"reason": reason})

    if name in {"unit_price", "delivery_fee", "discount", "line_total"}:
        _validate_money(client, value, reason=reason)
    elif name in {"quantity", "unit_size", "pack_count"}:
        result = _check_number(
            value,
            scale=0 if name == "pack_count" else 6,
            precision=10 if name == "pack_count" else 18,
            reason=reason,
        )
        if result <= 0 or (name == "pack_count" and result > 2147483647):
            reject()
    elif name == "vat_rate":
        result = _check_number(value, scale=4, precision=5, reason=reason)
        if not 0 <= result <= 1:
            reject()
    elif name == "pack_unit":
        _check_reference(client, "supported_base_unit", value, reason=reason)
    elif name in {"description", "original_text", "pack_text"}:
        if not isinstance(value, str) or not value.strip():
            reject()
    else:
        reject()
