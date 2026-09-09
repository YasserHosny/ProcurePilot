from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.catalogue.service import CatalogueService
from procurepilot_api.modules.landed_cost.service import LandedCostService
from procurepilot_api.modules.matching.alias_service import AliasLearningService
from procurepilot_api.modules.matching.schemas import MatchDecision, MatchResolutionRequest
from procurepilot_api.modules.matching.scoring import decimal_string
from procurepilot_api.modules.matching.service import (
    _candidate,
    _decision,
    _decision_for_line,
    _line_row,
)
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id


class MatchResolutionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._catalogue = CatalogueService(self._settings)
        self._aliases = AliasLearningService()
        self._landed_cost = LandedCostService(self._settings)

    def resolve(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        line_id: UUID,
        payload: MatchResolutionRequest,
    ) -> MatchDecision:
        client = authenticated_client(self._settings, bearer_token)
        line = _line_row(client, line_id)
        if _decision_for_line(client, line_id) is not None:
            raise ConflictError(details={"reason": "line_already_matched"})
        if payload.outcome == "no_match_new_product":
            if payload.create_product is None:
                raise ConflictError(details={"reason": "create_product_required"})
            product = self._catalogue.create_product(
                bearer_token=bearer_token, member=member, payload=payload.create_product
            )
            candidate_id = None
            product_id = product.id
            confidence = "1.0000"
        else:
            if payload.selected_match_candidate_id is None:
                raise ConflictError(details={"reason": "candidate_required"})
            candidate_row = self._candidate_row(
                client, payload.selected_match_candidate_id, line_id
            )
            _candidate(client, candidate_row)
            candidate_id = payload.selected_match_candidate_id
            product_id = UUID(str(candidate_row["candidate_workspace_product_id"]))
            confidence = decimal_string(candidate_row["confidence"])
        alias_id = self._aliases.learn_or_reuse_alias(
            client=client,
            tenant_id=member.tenant_id,
            membership_id=member.membership_id,
            workspace_product_id=product_id,
            supplier_id=self._quotation_supplier_id(client, UUID(str(line["quotation_id"]))),
            alias_text=str(line["original_text"]),
        )
        try:
            response = (
                client.table("match_decision")
                .insert(
                    {
                        "tenant_id": str(member.tenant_id),
                        "quotation_line_id": str(line_id),
                        "matched_workspace_product_id": str(product_id),
                        "selected_match_candidate_id": str(candidate_id) if candidate_id else None,
                        "outcome": payload.outcome,
                        "is_automatic": False,
                        "decided_by": str(member.membership_id),
                        "confidence": confidence,
                        "alias_id": str(alias_id),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        decision = _decision(client, _one_row(response.data, resource="match_decision"))
        self._resolve_open_task(client, line_id)
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="matching.resolved",
                target={
                    "quotation_id": str(line["quotation_id"]),
                    "quotation_line_id": str(line_id),
                    "decision_id": str(decision.id),
                    "candidate_id": str(candidate_id) if candidate_id else None,
                    "matched_product_id": str(decision.matched_product.id),
                    "outcome": decision.outcome,
                    "score": decision.confidence,
                },
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )
        self._landed_cost.compute_for_line_with_client(
            client=client, member=member, line_id=line_id
        )
        return decision

    def _candidate_row(
        self,
        client: object,
        candidate_id: UUID,
        line_id: UUID,
    ) -> dict[str, object]:
        try:
            rows = _rows(
                client.table("match_candidate")
                .select(
                    "id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,rank,scoring_version,embedding_model,created_at"
                )
                .eq("id", str(candidate_id))
                .eq("quotation_line_id", str(line_id))
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        if len(rows) != 1:
            raise ConflictError(details={"reason": "candidate_not_valid_for_line"})
        return rows[0]

    def _quotation_supplier_id(self, client: object, quotation_id: UUID) -> UUID | None:
        try:
            rows = _rows(
                client.table("quotation")
                .select("id,supplier_id")
                .eq("id", str(quotation_id))
                .limit(2)
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        row = _one_row(rows, resource="quotation")
        return UUID(str(row["supplier_id"])) if row.get("supplier_id") else None

    def _resolve_open_task(self, client: object, line_id: UUID) -> None:
        try:
            client.table("match_task").update(
                {"status": "resolved", "resolved_at": datetime.now(UTC).isoformat()}
            ).eq("quotation_line_id", str(line_id)).in_(
                "status", ["open", "in_progress"]
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def get_match_resolution_service() -> MatchResolutionService:
    return MatchResolutionService()


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"reason": "invalid_database_response"})


def _one_row(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise NotFoundError(details={"resource": resource})
    raise ServiceUnavailableError(details={"reason": "multiple_rows", "resource": resource})
