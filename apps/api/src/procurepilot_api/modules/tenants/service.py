from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ServiceUnavailableError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.service import AuthService
from procurepilot_api.modules.members.models import SessionResponse
from procurepilot_api.modules.tenants.invitations import (
    PlatformInvitationStore,
    PlatformInvitationValidator,
)
from procurepilot_api.modules.tenants.models import (
    ConfigOptions,
    PlatformInvitation,
    ReferenceOption,
    SignupRequest,
    Tenant,
    WorkspaceCreated,
)


class PostgresPlatformInvitationStore(PlatformInvitationStore):
    def __init__(self, cursor: psycopg.Cursor) -> None:
        self._cursor = cursor

    def get_by_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> PlatformInvitation | None:
        suffix = " for update" if for_update else ""
        self._cursor.execute(
            (
                "select id,email,token_hash,expires_at,status,spent_at,created_at "
                "from platform_invitation where token_hash = %s"
                f"{suffix}"
            ),
            (token_hash,),
        )
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PlatformInvitation.model_validate(row)

    def mark_spent(self, invitation: PlatformInvitation) -> None:
        self._cursor.execute(
            """
            update platform_invitation
               set status = 'spent',
                   spent_at = now()
             where id = %s
               and status = 'pending'
            """,
            (invitation.id,),
        )
        if self._cursor.rowcount != 1:
            raise ServiceUnavailableError(details={"reason": "invitation_spend_race"})


class TenantSignupRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def prevalidate(self, request: SignupRequest) -> None:
        try:
            with psycopg.connect(
                self._settings.database_url.get_secret_value(),
                row_factory=dict_row,
            ) as conn:
                with conn.cursor() as cur:
                    PlatformInvitationValidator(PostgresPlatformInvitationStore(cur)).require_valid(
                        invitation_token=request.invitation_token,
                        email=request.email,
                    )
                    self._validate_reference_rows(cur, request)
        except (UnprocessableEntityError, ServiceUnavailableError):
            raise
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def create_workspace(self, request: SignupRequest, user_id: UUID) -> WorkspaceCreated:
        try:
            with psycopg.connect(
                self._settings.database_url.get_secret_value(),
                row_factory=dict_row,
            ) as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        invitation_store = PostgresPlatformInvitationStore(cur)
                        invitation = PlatformInvitationValidator(invitation_store).require_valid(
                            invitation_token=request.invitation_token,
                            email=request.email,
                            for_update=True,
                        )
                        self._validate_reference_rows(cur, request)
                        tenant = self._insert_tenant(cur, request, invitation.id)
                        membership_id = self._insert_owner_membership(
                            cur,
                            tenant_id=tenant.id,
                            user_id=user_id,
                            email=request.email,
                        )
                        invitation_store.mark_spent(invitation)
                        self._record_tenant_created(cur, tenant, membership_id, request.email)
                        return WorkspaceCreated(
                            tenant=tenant,
                            membership_id=membership_id,
                            user_id=user_id,
                            email=request.email,
                            role=MemberRole.owner,
                        )
        except (UnprocessableEntityError, ServiceUnavailableError):
            raise
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def config_options(self) -> ConfigOptions:
        try:
            with psycopg.connect(
                self._settings.database_url.get_secret_value(),
                row_factory=dict_row,
            ) as conn:
                with conn.cursor() as cur:
                    return ConfigOptions(
                        regions=self._reference_options(cur, "supported_region"),
                        currencies=self._reference_options(cur, "supported_currency"),
                        tax_models=self._reference_options(cur, "supported_tax_model"),
                    )
        except psycopg.Error as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def _validate_reference_rows(self, cur: psycopg.Cursor, request: SignupRequest) -> None:
        checks = (
            ("region", "supported_region", request.region),
            ("currency", "supported_currency", request.currency),
            ("tax_model", "supported_tax_model", request.tax_model),
        )
        for field, table, code in checks:
            cur.execute(
                f"select exists(select 1 from {table} where code = %s and is_enabled)",
                (code,),
            )
            row = cur.fetchone()
            if row is None or not row["exists"]:
                raise UnprocessableEntityError(details={field: "unsupported"})

    def _insert_tenant(
        self,
        cur: psycopg.Cursor,
        request: SignupRequest,
        invitation_id: UUID,
    ) -> Tenant:
        for slug in _candidate_slugs(request.business_name):
            cur.execute("select exists(select 1 from tenant where slug = %s)", (slug,))
            row = cur.fetchone()
            if row is not None and not row["exists"]:
                cur.execute(
                    """
                    insert into tenant (
                      name, slug, region, currency, tax_model,
                      default_locale, platform_invitation_id
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    returning id,name,slug,region,currency,tax_model,default_locale,created_at
                    """,
                    (
                        request.business_name,
                        slug,
                        request.region,
                        request.currency,
                        request.tax_model,
                        request.default_locale,
                        invitation_id,
                    ),
                )
                inserted = cur.fetchone()
                if inserted is None:
                    break
                return Tenant.model_validate(inserted)
        raise ServiceUnavailableError(details={"reason": "slug_generation_failed"})

    def _insert_owner_membership(
        self,
        cur: psycopg.Cursor,
        *,
        tenant_id: UUID,
        user_id: UUID,
        email: str,
    ) -> UUID:
        cur.execute(
            """
            update membership
               set is_active_workspace = false
             where user_id = %s
               and is_active_workspace
            """,
            (user_id,),
        )
        cur.execute(
            """
            insert into membership (
              tenant_id, user_id, email, role, is_active_workspace, status
            )
            values (%s, %s, %s, 'owner', true, 'active')
            returning id
            """,
            (tenant_id, user_id, email),
        )
        row = cur.fetchone()
        if row is None:
            raise ServiceUnavailableError(details={"reason": "membership_insert_failed"})
        return row["id"]

    def _record_tenant_created(
        self,
        cur: psycopg.Cursor,
        tenant: Tenant,
        membership_id: UUID,
        email: str,
    ) -> None:
        cur.execute(
            """
            select record_audit_event(
              'tenant.created',
              'success',
              %s::uuid,
              %s::uuid,
              %s,
              jsonb_build_object('tenant_id', %s::text, 'slug', %s)
            )
            """,
            (tenant.id, membership_id, email, tenant.id, tenant.slug),
        )

    def _reference_options(self, cur: psycopg.Cursor, table: str) -> list[ReferenceOption]:
        cur.execute(
            f"""
            select code,label_en,label_ar
              from {table}
             where is_enabled
             order by code
            """
        )
        return [ReferenceOption.model_validate(row) for row in cur.fetchall()]


class TenantSignupService:
    def __init__(
        self,
        repository: TenantSignupRepository | None = None,
        auth_service: AuthService | None = None,
    ) -> None:
        self._repository = repository or TenantSignupRepository()
        self._auth_service = auth_service or AuthService()

    def signup(self, request: SignupRequest) -> SessionResponse:
        self._repository.prevalidate(request)
        user_id = self._auth_service.create_auth_user(
            email=request.email,
            password=request.password,
        )
        self._repository.create_workspace(request, user_id)
        return self._auth_service.login(email=request.email, password=request.password)


def _candidate_slugs(name: str) -> Sequence[str]:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if len(base) < 3:
        base = f"{base}-workspace".strip("-")
    base = base[:63].strip("-")
    if len(base) < 3:
        base = "workspace"
    return (base, f"{base[:54].strip('-')}-{uuid4().hex[:8]}")


def get_tenant_signup_service() -> TenantSignupService:
    return TenantSignupService()


def get_tenant_signup_repository() -> TenantSignupRepository:
    return TenantSignupRepository()
