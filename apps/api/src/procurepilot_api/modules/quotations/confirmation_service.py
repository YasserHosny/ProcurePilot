from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.quotations.review_gate import blocking_low_confidence_fields
from procurepilot_api.modules.quotations.schemas import ConfirmRequest, Quotation
from procurepilot_api.modules.quotations.service import _one_row, _quotation
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

logger = logging.getLogger(__name__)


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
            if not (payload and payload.acknowledge_mismatch):
                raise ConflictError(details={"reason": "arithmetic_mismatch_unresolved"})
        if quote.get("currency") is None:
            raise ConflictError(details={"reason": "currency_unresolved"})

        low_confidence = blocking_low_confidence_fields(
            client,
            quotation_id,
            self._settings.extraction_confidence_threshold,
            supplier_id=quote.get("supplier_id"),
        )
        if low_confidence:
            raise ConflictError(
                details={"reason": "low_confidence_unresolved", "fields": low_confidence[:100]}
            )

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
            supplier_name_rows = []
            if quote.get("supplier_id") is not None:
                supplier_name_rows = (
                    client.table("field_extraction")
                    .select("id,extracted_value")
                    .eq("quotation_id", str(quotation_id))
                    .eq("field_name", "supplier_name")
                    .is_("corrected_by", "null")
                    .lt("confidence", self._settings.extraction_confidence_threshold)
                    .execute()
                    .data
                )
                for evidence in supplier_name_rows:
                    client.table("field_extraction").update(
                        {
                            "corrected_by": str(member.membership_id),
                            "corrected_at": datetime.now(UTC).isoformat(),
                            "corrected_value": evidence.get("extracted_value"),
                        }
                    ).eq("id", str(evidence["id"])).execute()
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
            # Human confirmation is the authorisation that clears any sticky extraction reason.
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="quotation.confirmed",
                target=_confirmation_audit_target(quotation_id, supplier_name_rows),
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )
        # Each PostgREST mutation above has committed before matching starts. Reuse the
        # GET pipeline with the caller's JWT; preparation is best effort and retryable.
        try:
            MatchingService(self._settings).quotation_matches(
                bearer_token=bearer_token, member=member, quotation_id=quotation_id
            )
        except Exception:
            logger.exception("Failed to prepare matching for quotation %s", quotation_id)
        return _quotation(rows)


def _confirmation_audit_target(
    quotation_id: UUID, supplier_name_rows: list[dict[str, object]]
) -> dict[str, object]:
    target: dict[str, object] = {"quotation_id": str(quotation_id)}
    if supplier_name_rows:
        target["resolved_on_confirm"] = [
            {
                "field_extraction_id": str(row["id"]),
                "field_name": "supplier_name",
                "resolution": "supplier_selected",
            }
            for row in supplier_name_rows
        ]
    return target


def get_quotation_confirmation_service() -> QuotationConfirmationService:
    return QuotationConfirmationService()
