from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import (
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
            .select("id,status,supplier_id,reviewer_notes")
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

        if "reviewer_notes" in patch.model_fields_set:
            updates["reviewer_notes"] = patch.reviewer_notes

        try:
            client.table("quotation").update(updates).eq("id", str(quotation_id)).execute()
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
                if field.get("corrected_by") is not None:
                    continue
                client.table("field_extraction").update(
                    {
                        "corrected_value": correction.corrected_value,
                        "corrected_by": str(member.membership_id),
                        "corrected_at": datetime.now(UTC).isoformat(),
                    }
                ).eq("id", str(correction.field_extraction_id)).execute()
                _apply_correction_to_canonical_row(client, field, correction.corrected_value)

            for line_id in patch.remove_line_ids:
                client.table("field_extraction").delete().eq(
                    "entity_id", str(line_id)
                ).eq("entity_type", "quotation_line").execute()
                client.table("quotation_line").delete().eq(
                    "id", str(line_id)
                ).eq("quotation_id", str(quotation_id)).execute()

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

                q_row = (
                    client.table("quotation")
                    .select("tenant_id")
                    .eq("id", str(quotation_id))
                    .limit(1)
                    .execute()
                    .data
                )
                q_tenant_id = q_row[0]["tenant_id"] if q_row else None
                if q_tenant_id is None:
                    raise ServiceUnavailableError(details={"reason": "quotation_not_found"})

                for new_line in patch.add_lines:
                    row_data: dict[str, object] = {
                        "tenant_id": q_tenant_id,
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
                .update({
                    "status": "refused",
                    "reviewed_by": str(member.membership_id),
                    "reviewed_at": datetime.now(UTC).isoformat(),
                })
                .eq("id", str(quotation_id))
                .execute()
                .data,
                resource="quotation",
            )
            client.table("review_task").update(
                {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
            ).eq("quotation_id", str(quotation_id)).in_(
                "status", ["open", "in_progress"]
            ).execute()
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
        if field_name == "quantity":
            client.table("quotation_line").update({"quantity": corrected_value}).eq(
                "id", entity_id
            ).execute()
        elif field_name == "unit_price" and isinstance(corrected_value, dict):
            amount = corrected_value.get("amount")
            currency = corrected_value.get("currency")
            if amount is not None and currency is not None:
                client.table("quotation_line").update(
                    {"unit_price_amount": amount, "unit_price_currency": currency}
                ).eq("id", entity_id).execute()
    elif entity_type == "quotation":
        if field_name in {"currency", "issue_date", "expiry_date"} and isinstance(
            corrected_value, str
        ):
            client.table("quotation").update({field_name: corrected_value}).eq(
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
        .select("id,stated_total_amount,arithmetic_status")
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
        subtotal += line_net * (1 + vat_rate)
    if not has_line_total:
        return
    stated = Decimal(str(stated_amount))
    if abs(subtotal - stated) <= ARITHMETIC_TOLERANCE:
        status = "reconciled"
    elif not has_any_vat and subtotal > 0 and stated > subtotal:
        inferred_pct = round(
            float((stated - subtotal) / subtotal) * 100
        )
        if 0 < inferred_pct <= 30:
            recomputed = subtotal * (
                1 + Decimal(str(inferred_pct)) / 100
            )
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
    open_task_query = client.table("review_task").select("id").eq(
        "quotation_id", str(quotation_id)
    ).in_("status", ["open", "in_progress"])
    open_tasks = _rows(open_task_query.execute().data)

    if blocker is None:
        client.table("review_task").update(
            {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
        ).eq("quotation_id", str(quotation_id)).in_(
            "status", ["open", "in_progress"]
        ).execute()
        return

    reason, priority = blocker
    payload: dict[str, object] = {
        "reason": reason,
        "priority": priority,
        "status": "open",
        "resolved_at": None,
    }
    if open_tasks:
        client.table("review_task").update(payload).eq(
            "quotation_id", str(quotation_id)
        ).in_("status", ["open", "in_progress"]).execute()
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
        .select("id,supplier_id,arithmetic_status")
        .eq("id", str(quotation_id))
        .limit(2)
        .execute()
        .data,
        resource="quotation",
    )
    if quote.get("arithmetic_status") == "mismatch":
        return ("arithmetic_mismatch", "high")

    low_confidence = (
        client.table("field_extraction")
        .select("id")
        .eq("quotation_id", str(quotation_id))
        .lt("confidence", confidence_threshold)
        .is_("corrected_by", "null")
        .limit(1)
        .execute()
        .data
    )
    if low_confidence:
        return ("low_confidence", "normal")
    if quote.get("supplier_id") is None:
        return ("no_supplier_match", "normal")
    return None


def get_quotation_review_service() -> QuotationReviewService:
    return QuotationReviewService()
