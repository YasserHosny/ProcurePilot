from __future__ import annotations

import hashlib
import json
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
        idempotency_key: UUID | None = None,
    ) -> MatchDecision:
        client = authenticated_client(self._settings, bearer_token)
        fingerprint = _request_fingerprint(payload)
        if idempotency_key is not None:
            existing_request = _idempotency_record_for_key(
                client, member.tenant_id, idempotency_key
            )
            if existing_request is not None:
                if (
                    str(existing_request["quotation_line_id"]) != str(line_id)
                    or str(existing_request["request_fingerprint"]) != fingerprint
                ):
                    raise ConflictError(details={"reason": "idempotency_key_reused"})
                return _decision(
                    client,
                    _decision_by_id(client, UUID(str(existing_request["match_decision_id"]))),
                )
        line = _line_row(client, line_id)
        existing_decision = _decision_for_line(client, line_id)
        if existing_decision is not None:
            if idempotency_key is not None and _decision_matches_payload(
                existing_decision, payload
            ):
                decision = _decision(client, existing_decision)
                self._complete_resolution_side_effects(
                    client=client,
                    bearer_token=bearer_token,
                    member=member,
                    line=line,
                    line_id=line_id,
                    decision=decision,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    repair_existing_decision=True,
                )
                return decision
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
        self._complete_resolution_side_effects(
            client=client,
            bearer_token=bearer_token,
            member=member,
            line=line,
            line_id=line_id,
            decision=decision,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            repair_existing_decision=False,
        )
        return decision

    def _complete_resolution_side_effects(
        self,
        *,
        client: object,
        bearer_token: str,
        member: CurrentMember,
        line: dict[str, object],
        line_id: UUID,
        decision: MatchDecision,
        idempotency_key: UUID | None,
        request_fingerprint: str,
        repair_existing_decision: bool,
    ) -> None:
        self._resolve_open_task(client, line_id)
        if not repair_existing_decision or not _matching_resolution_audit_exists(
            client, decision.id
        ):
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
                        "candidate_id": (
                            str(decision.selected_match_candidate_id)
                            if decision.selected_match_candidate_id
                            else None
                        ),
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
        if idempotency_key is not None:
            _record_idempotency_decision(
                client=client,
                member=member,
                idempotency_key=idempotency_key,
                line_id=line_id,
                request_fingerprint=request_fingerprint,
                decision_id=decision.id,
            )

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
            ).eq("quotation_line_id", str(line_id)).in_("status", ["open", "in_progress"]).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def get_match_resolution_service() -> MatchResolutionService:
    return MatchResolutionService()


def _request_fingerprint(payload: MatchResolutionRequest) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decision_matches_payload(
    decision: dict[str, object],
    payload: MatchResolutionRequest,
) -> bool:
    if str(decision.get("outcome")) != payload.outcome:
        return False
    if payload.outcome == "no_match_new_product":
        return False
    return str(decision.get("selected_match_candidate_id")) == str(
        payload.selected_match_candidate_id
    )


def _matching_resolution_audit_exists(client: object, decision_id: UUID) -> bool:
    try:
        rows = _rows(
            client.table("audit_event")
            .select("id")
            .eq("action", "matching.resolved")
            .eq("target->>decision_id", str(decision_id))
            .limit(1)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "audit_event"}) from exc
    return bool(rows)


def _idempotency_record_for_key(
    client: object,
    tenant_id: UUID,
    idempotency_key: UUID,
) -> dict[str, object] | None:
    try:
        rows = _rows(
            client.table("match_resolution_idempotency")
            .select(
                "tenant_id,idempotency_key,quotation_line_id,request_fingerprint,match_decision_id,created_at"
            )
            .eq("tenant_id", str(tenant_id))
            .eq("idempotency_key", str(idempotency_key))
            .limit(2)
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    if len(rows) > 1:
        raise ServiceUnavailableError(details={"reason": "multiple_idempotency_records"})
    return rows[0] if rows else None


def _decision_by_id(client: object, decision_id: UUID) -> dict[str, object]:
    try:
        response = (
            client.table("match_decision")
            .select(
                "id,quotation_line_id,matched_workspace_product_id,selected_match_candidate_id,outcome,"
                "is_automatic,decided_by,decided_at,confidence,alias_id,created_at"
            )
            .eq("id", str(decision_id))
            .limit(2)
            .execute()
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _one_row(response.data, resource="match_decision")


def _record_idempotency_decision(
    *,
    client: object,
    member: CurrentMember,
    idempotency_key: UUID,
    line_id: UUID,
    request_fingerprint: str,
    decision_id: UUID,
) -> None:
    try:
        client.table("match_resolution_idempotency").insert(
            {
                "tenant_id": str(member.tenant_id),
                "idempotency_key": str(idempotency_key),
                "quotation_line_id": str(line_id),
                "request_fingerprint": request_fingerprint,
                "match_decision_id": str(decision_id),
            }
        ).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


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
