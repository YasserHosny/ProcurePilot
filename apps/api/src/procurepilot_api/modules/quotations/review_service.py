from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import QuotationDetail, QuotationReviewPatch
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
            .select("id,status")
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
            _recompute_arithmetic_status(client, quotation_id)
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
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


def get_quotation_review_service() -> QuotationReviewService:
    return QuotationReviewService()
