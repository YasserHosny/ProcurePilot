from __future__ import annotations

from uuid import UUID

from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.members.models import Me, MeUpdate, WorkspaceList, WorkspaceSummary
from procurepilot_api.modules.tenants.models import Tenant
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer


def authenticated_client(settings: Settings, bearer_token: str) -> Client:
    client = create_client(settings.supabase_url, settings.supabase_anon_key.get_secret_value())
    client.postgrest.auth(bearer_token)
    return client


def load_me_for_token(settings: Settings, bearer_token: str, member: CurrentMember) -> Me:
    client = authenticated_client(settings, bearer_token)
    tenant_rows = _rows(
        client.table("tenant")
        .select("id,name,slug,region,currency,tax_model,default_locale,created_at")
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


def require_refresh_token(refresh_token: str | None) -> str:
    if not refresh_token:
        raise UnprocessableEntityError(details={"refresh_token": "required_to_reissue_session"})
    return refresh_token


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def get_member_service() -> MemberService:
    return MemberService()
