from __future__ import annotations

import base64
import json
import logging
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.models import (
    Me,
    Member,
    MemberList,
    MemberRoleUpdate,
    MeUpdate,
    WorkspaceList,
    WorkspaceSummary,
)
from procurepilot_api.modules.organisation.schemas import (
    BranchRoleAssignment,
    BranchRoleAssignmentCreate,
)
from procurepilot_api.modules.tenants.models import Tenant
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

logger = logging.getLogger(__name__)


def authenticated_client(settings: Settings, bearer_token: str) -> Client:
    client = create_client(settings.supabase_url, settings.supabase_anon_key.get_secret_value())
    client.postgrest.auth(bearer_token)
    return client


def load_me_for_token(settings: Settings, bearer_token: str, member: CurrentMember) -> Me:
    client = authenticated_client(settings, bearer_token)
    tenant_rows = _rows(
        client.table("tenant")
        .select("id,name,slug,region,currency,tax_model,default_locale,reporting_timezone,created_at")
        .eq("id", str(member.tenant_id))
        .limit(2)
        .execute()
        .data
    )
    membership_rows = _rows(
        client.table("membership")
        .select("preferred_locale,mfa_enabled")
        .eq("id", str(member.membership_id))
        .limit(2)
        .execute()
        .data
    )
    if len(tenant_rows) != 1 or len(membership_rows) != 1:
        raise NotFoundError(details={"resource": "current_member"})
    membership = membership_rows[0]
    return Me(
        id=member.user_id,
        email=member.email,
        role=member.role,
        preferred_locale=membership.get("preferred_locale"),
        mfa_enabled=bool(membership.get("mfa_enabled", False)),
        tenant=Tenant.model_validate(tenant_rows[0]),
    )


class MemberService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def update_me(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        patch: MeUpdate,
    ) -> Me:
        client = authenticated_client(self._settings, bearer_token)
        payload = patch.model_dump(exclude_none=True)
        if payload:
            client.table("membership").update(payload).eq("id", str(member.membership_id)).execute()
        return load_me_for_token(self._settings, bearer_token, member)

    def list_workspaces(self, *, bearer_token: str, member: CurrentMember) -> WorkspaceList:
        """Every workspace the caller belongs to.

        Goes through the `list_my_workspaces` RPC (migration 0008) rather than querying
        `membership` directly. Two reasons, and the second is the important one:

        * membership RLS is scoped to the ACTIVE workspace, so a direct query can only ever
          return the workspace the token already names — the answer is structurally wrong.
        * the alternative, opening a privileged connection and filtering by user_id in Python,
          puts an RLS bypass in the request path. That is what Constitution Principle V forbids,
          and it would set the pattern every later chunk copies.

        The RPC takes no user parameter: it reads the caller from the JWT, so it cannot be
        pointed at somebody else.
        """
        del member  # identity comes from the token the RPC reads, never from the caller's word
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.rpc("list_my_workspaces", {}).execute()
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return WorkspaceList(
            items=[WorkspaceSummary.model_validate(row) for row in _rows(response.data)]
        )

    def switch_active_workspace(
        self, *, bearer_token: str, member: CurrentMember, tenant_id: UUID
    ) -> None:
        """Move the caller's active workspace.

        `set_active_workspace` returns false rather than raising when the caller is not a member
        of the target: whether a workspace exists is itself information, so this must look like
        "not found", never "forbidden" (FR-005).
        """
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.rpc(
                "set_active_workspace", {"p_tenant_id": str(tenant_id)}
            ).execute()
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        if response.data is not True:
            raise NotFoundError(details={"resource": "workspace"})

        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="member.active_workspace_switched",
                target={"tenant_id": str(tenant_id)},
                outcome="success",
            ),
            bearer_token=bearer_token,
        )

    def list_members(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MemberList:
        client = authenticated_client(self._settings, bearer_token)
        capped_limit = max(1, min(limit, 100))
        offset = _decode_cursor(cursor)
        try:
            response = (
                client.table("membership")
                .select("id,email,role,status,mfa_enabled,created_at")
                .order("created_at")
                .order("id")
                .range(offset, offset + capped_limit)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        visible_rows = rows[:capped_limit]
        next_cursor = _encode_cursor(offset + capped_limit) if len(rows) > capped_limit else None
        return MemberList(
            items=[Member.model_validate(row) for row in visible_rows],
            next_cursor=next_cursor,
        )

    def update_member_role(
        self,
        *,
        bearer_token: str,
        actor: CurrentMember,
        member_id: UUID,
        patch: MemberRoleUpdate,
    ) -> Member:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("membership")
                .update({"role": patch.role.value})
                .eq("id", str(member_id))
                .execute()
            )
        except APIError as exc:
            raise _member_update_error(exc) from exc

        updated = _one_member(response.data)
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=actor.tenant_id,
                actor_membership_id=actor.membership_id,
                actor_email=actor.email,
                action="member.role_changed",
                target={"member_id": str(member_id), "role": patch.role.value},
                outcome="success",
            ),
            bearer_token=bearer_token,
        )
        return updated

    def remove_member(
        self,
        *,
        bearer_token: str,
        actor: CurrentMember,
        member_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("membership")
                # No `.select()` after `.update()` — unsupported by the pinned supabase-py
                # builder; `.execute()` returns the updated representation anyway.
                .update({"status": "removed", "is_active_workspace": False})
                .eq("id", str(member_id))
                .execute()
            )
        except APIError as exc:
            raise _member_update_error(exc) from exc

        _one_member(response.data)
        try:
            client.table("cost_centre").update({"is_orphaned": True}).eq(
                "budget_owner_membership_id", str(member_id)
            ).execute()
        except APIError:
            logger.warning(
                "Could not mark cost centres orphaned after member removal",
                extra={"member_id": str(member_id)},
                exc_info=True,
            )
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=actor.tenant_id,
                actor_membership_id=actor.membership_id,
                actor_email=actor.email,
                action="member.removed",
                target={"member_id": str(member_id)},
                outcome="success",
            ),
            bearer_token=bearer_token,
        )

        # FR-009: a removed member may still be the assigned approver on pending requests. Re-route
        # those to the owner now that the membership is marked removed. Best-effort — the removal
        # itself has already committed and must not be undone if this follow-up fails; the requests
        # module records its own audit entry per escalated step. Imported lazily because
        # requests.service imports from this module.
        try:
            from procurepilot_api.modules.requests.service import RequestsService

            RequestsService(self._settings).escalate_pending_steps_for_removed_member(
                bearer_token=bearer_token,
                actor=actor,
                removed_membership_id=member_id,
            )
        except Exception:
            logger.warning(
                "Could not escalate pending approval steps after member removal",
                extra={"member_id": str(member_id)},
                exc_info=True,
            )

    def create_branch_role_assignment(
        self,
        *,
        bearer_token: str,
        actor: CurrentMember,
        payload: BranchRoleAssignmentCreate,
    ) -> BranchRoleAssignment:
        client = authenticated_client(self._settings, bearer_token)
        try:
            membership_response = (
                client.table("membership")
                .select("id,tenant_id,role")
                .eq("id", str(payload.membership_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        membership = _one_row(
            _rows(membership_response.data),
            resource="member",
            ambiguous_reason="member_read_ambiguous",
        )
        if str(membership.get("role", "")) not in {
            MemberRole.branch_manager.value,
            MemberRole.approver.value,
        }:
            raise UnprocessableEntityError(
                details={"reason": "branch_scopable_role_required"}
            )

        try:
            branch_response = (
                client.table("branch")
                .select("id")
                .eq("id", str(payload.branch_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        _one_row(
            _rows(branch_response.data),
            resource="branch",
            ambiguous_reason="branch_read_ambiguous",
        )

        try:
            response = (
                client.table("branch_role_assignment")
                .insert(
                    {
                        "tenant_id": str(membership["tenant_id"]),
                        "membership_id": str(payload.membership_id),
                        "branch_id": str(payload.branch_id),
                    }
                )
                .execute()
            )
        except APIError as exc:
            raise _branch_role_assignment_insert_error(exc) from exc

        assignment = _one_branch_role_assignment(response.data)
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=actor.tenant_id,
                actor_membership_id=actor.membership_id,
                actor_email=actor.email,
                action="member.branch_role_assignment_created",
                target={
                    "assignment_id": str(assignment.id),
                    "member_id": str(payload.membership_id),
                    "branch_id": str(payload.branch_id),
                },
                outcome="success",
            ),
            bearer_token=bearer_token,
        )
        return assignment

    def remove_branch_role_assignment(
        self,
        *,
        bearer_token: str,
        actor: CurrentMember,
        assignment_id: UUID,
    ) -> None:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("branch_role_assignment")
                # No `.select()` after `.update()`/`.delete()` — unsupported by the pinned
                # supabase-py builder; `.execute()` returns the affected representation anyway.
                .delete()
                .eq("id", str(assignment_id))
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        assignment = _one_branch_role_assignment(response.data)
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=actor.tenant_id,
                actor_membership_id=actor.membership_id,
                actor_email=actor.email,
                action="member.branch_role_assignment_removed",
                target={
                    "assignment_id": str(assignment.id),
                    "member_id": str(assignment.membership_id),
                    "branch_id": str(assignment.branch_id),
                },
                outcome="success",
            ),
            bearer_token=bearer_token,
        )


def require_refresh_token(refresh_token: str | None) -> str:
    if not refresh_token:
        raise UnprocessableEntityError(details={"refresh_token": "required_to_reissue_session"})
    return refresh_token


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _one_row(
    rows: list[dict[str, object]],
    *,
    resource: str,
    ambiguous_reason: str,
) -> dict[str, object]:
    if len(rows) == 0:
        raise NotFoundError(details={"resource": resource})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": ambiguous_reason})
    return rows[0]


def _one_member(data: object) -> Member:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": "member"})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": "member_write_ambiguous"})
    return Member.model_validate(rows[0])


def _one_branch_role_assignment(data: object) -> BranchRoleAssignment:
    rows = _rows(data)
    if len(rows) == 0:
        raise NotFoundError(details={"resource": "branch_role_assignment"})
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": "branch_role_assignment_write_ambiguous"})
    return BranchRoleAssignment.model_validate(rows[0])


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


def _member_update_error(exc: APIError) -> ConflictError | ServiceUnavailableError:
    code = str(getattr(exc, "code", ""))
    message = str(getattr(exc, "message", ""))
    if code == "23001" or "retain at least one active owner" in message:
        return ConflictError(details={"reason": "last_owner"})
    return ServiceUnavailableError(details={"dependency": "database"})


def _branch_role_assignment_insert_error(
    exc: APIError,
) -> ConflictError | ServiceUnavailableError:
    if str(getattr(exc, "code", "")) == "23505":
        return ConflictError(details={"reason": "already_assigned_to_branch"})
    return ServiceUnavailableError(details={"dependency": "database"})


def get_member_service() -> MemberService:
    return MemberService()
