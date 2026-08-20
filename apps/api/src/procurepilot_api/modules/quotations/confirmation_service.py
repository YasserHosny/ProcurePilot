from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import ConfirmRequest, Quotation
from procurepilot_api.modules.quotations.service import _one_row, _quotation


class QuotationConfirmationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def confirm(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        quotation_id: UUID,
        payload: ConfirmRequest | None,
    ) -> Quotation:
        client = authenticated_client(self._settings, bearer_token)
        quote = _one_row(
            client.table("quotation")
            .select(
                "id,document_id,supplier_id,currency,issue_date,expiry_date,status,"
                "previous_quotation_id,stated_total_amount,stated_total_currency,"
                "arithmetic_status,created_at,reviewed_by,reviewed_at"
            )
            .eq("id", str(quotation_id))
            .limit(2)
            .execute()
            .data,
            resource="quotation",
        )
        if quote["status"] not in {"extracted", "in_review"}:
            raise ConflictError(details={"reason": "quotation_not_confirmable"})
        if quote.get("supplier_id") is None:
            raise ConflictError(details={"reason": "supplier_not_confirmed"})
        if quote.get("arithmetic_status") == "mismatch":
            raise ConflictError(details={"reason": "arithmetic_mismatch_unresolved"})

        threshold = self._settings.extraction_confidence_threshold
        try:
            low_confidence = client.table("field_extraction").select("id,confidence").eq(
                "quotation_id", str(quotation_id)
            ).lt("confidence", threshold).is_("corrected_by", "null").limit(1).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if low_confidence.data:
            raise ConflictError(details={"reason": "low_confidence_unresolved"})

        previous_id = payload.previous_quotation_id if payload else None
        if previous_id is not None:
            if previous_id == quotation_id:
                raise ConflictError(details={"reason": "previous_quotation_self_reference"})
            _one_row(
                client.table("quotation")
                .select("id,supplier_id,status")
                .eq("id", str(previous_id))
                .eq("supplier_id", str(quote["supplier_id"]))
                .limit(2)
                .execute()
                .data,
                resource="previous_quotation",
            )

        try:
            rows = _one_row(
                client.table("quotation")
                .update(
                    {
                        "status": "reviewed",
                        "reviewed_by": str(member.membership_id),
                        "reviewed_at": datetime.now(UTC).isoformat(),
                        "previous_quotation_id": str(previous_id) if previous_id else None,
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
        return _quotation(rows)


def get_quotation_confirmation_service() -> QuotationConfirmationService:
    return QuotationConfirmationService()
