from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.schemas import QuotationDetail, QuotationReviewPatch
from procurepilot_api.modules.quotations.service import FIELD_COLUMNS, QuotationService, _one_row


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
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return QuotationService(self._settings).get_quotation(
            bearer_token=bearer_token, quotation_id=quotation_id
        )


def get_quotation_review_service() -> QuotationReviewService:
    return QuotationReviewService()
