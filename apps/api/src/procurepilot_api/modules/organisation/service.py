from __future__ import annotations

import base64
import json
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.organisation.schemas import (
    Branch,
    BranchCreate,
    BranchList,
    BranchUpdate,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

BRANCH_COLUMNS = "id,name,address,region,is_active,created_at,updated_at"


class OrganisationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_branches(
        self,
        *,
        bearer_token: str,
        is_active: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> BranchList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = _cap_limit(limit)
        offset = _decode_cursor(cursor)
        try:
            query = client.table("branch").select(BRANCH_COLUMNS)
            if is_active is not None:
                query = query.eq("is_active", is_active)
            response = query.order("created_at").order("id").range(
                offset,
                offset + capped_limit,
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        rows = _rows(response.data)
        visible_rows = rows[:capped_limit]
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        return BranchList(
            items=[_branch(row) for row in visible_rows],
            next_cursor=next_cursor,
        )

    def create_branch(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: BranchCreate,
    ) -> Branch:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.table("branch").insert(
                {
                    "tenant_id": str(member.tenant_id),
                    "name": payload.name,
                    "address": payload.address,
                    "region": payload.region,
                }
            ).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="branch_conflict") from exc

        branch = _branch(_one_row(response.data, reason="branch_write_failed"))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="organisation.branch_created",
            target={"branch_id": str(branch.id)},
        )
        return branch

    def update_branch(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        branch_id: UUID,
        patch: BranchUpdate,
    ) -> Branch:
        client = authenticated_client(self._settings, bearer_token)
        existing = self._branch_row(client, branch_id)
        updates: dict[str, object] = {}
        for field in ("name", "address", "region", "is_active"):
            if field in patch.model_fields_set:
                updates[field] = getattr(patch, field)

        if (
            "is_active" in patch.model_fields_set
            and patch.is_active is False
            and patch.confirm_dependents is not True
        ):
            dependent_counts = self._dependent_counts(client, branch_id)
            if any(dependent_counts.values()):
                raise UnprocessableEntityError(
                    details={
                        "reason": "dependents_confirmation_required",
                        **dependent_counts,
                    }
                )

        if not updates:
            return _branch(existing)

        try:
            response = client.table("branch").update(updates).eq("id", str(branch_id)).execute()
        except APIError as exc:
            raise _write_error(exc, duplicate_reason="branch_update_conflict") from exc

        branch = _branch(_one_row_or_not_found(response.data, resource="branch"))
        self._record(
            bearer_token=bearer_token,
            member=member,
            action="organisation.branch_updated",
            target={"branch_id": str(branch_id)},
        )
        return branch

    def _branch_row(self, client: Client, branch_id: UUID) -> dict[str, object]:
        try:
            response = (
                client.table("branch")
                .select(BRANCH_COLUMNS)
                .eq("id", str(branch_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_row_or_not_found(response.data, resource="branch")

    def _dependent_counts(self, client: Client, branch_id: UUID) -> dict[str, int]:
        try:
            cost_centres = _rows(
                client.table("cost_centre")
                .select("id")
                .eq("branch_id", str(branch_id))
                .execute()
                .data
            )
            branch_role_assignments = _rows(
                client.table("branch_role_assignment")
                .select("id")
                .eq("branch_id", str(branch_id))
                .execute()
                .data
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return {
            "cost_centre_count": len(cost_centres),
            "branch_role_assignment_count": len(branch_role_assignments),
        }

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
            ),
            bearer_token=bearer_token,
        )


def _branch(row: dict[str, object]) -> Branch:
    return Branch.model_validate(row)


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _one_row(data: object, *, reason: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": reason})
    return rows[0]


def _one_row_or_not_found(data: object, *, resource: str) -> dict[str, object]:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": f"{resource}_write_ambiguous"})
    return rows[0]


def _cap_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        offset = payload["offset"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if not isinstance(offset, int) or offset < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return offset


def _write_error(
    exc: APIError,
    *,
    duplicate_reason: str,
) -> ConflictError | ServiceUnavailableError | UnprocessableEntityError:
    code = _api_error_code(exc)
    if code in {"23503", "23514", "22P02"}:
        return UnprocessableEntityError(details={"reason": "database_constraint"})
    if code == "23505":
        return ConflictError(details={"reason": duplicate_reason})
    return ServiceUnavailableError(details={"dependency": "database"})


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None


def get_organisation_service() -> OrganisationService:
    return OrganisationService()
