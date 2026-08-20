from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    InvitationRefusedError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.models import MemberInvitation, Membership
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

INVITATION_COLUMNS = (
    "id,tenant_id,email,role,token_hash,invited_by,expires_at,status,created_at"
)


class MemberInvitationRecord(MemberInvitation):
    tenant_id: UUID
    token_hash: str
    invited_by: UUID
    created_at: datetime | None = None


class MemberInvitationRepository(Protocol):
    def issue(
        self,
        *,
        bearer_token: str,
        tenant_id: UUID,
        invited_by: UUID,
        email: str,
        role: MemberRole,
        token_hash: str,
        expires_at: datetime,
    ) -> MemberInvitationRecord:
        pass

    def list_pending(self, *, bearer_token: str) -> list[MemberInvitationRecord]:
        pass

    def revoke(
        self,
        *,
        bearer_token: str,
        invitation_id: UUID,
    ) -> MemberInvitationRecord | None:
        pass

    def get_by_hash(self, token_hash: str) -> MemberInvitationRecord | None:
        pass

    def mark_expired(self, invitation_id: UUID) -> None:
        pass

    def mark_accepted(self, invitation_id: UUID) -> None:
        pass

    def accept(
        self,
        *,
        bearer_token: str,
        invitation: MemberInvitationRecord,
        user_id: UUID,
        email: str,
        token_hash: str,
    ) -> Membership:
        pass

    def find_membership(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        pass


class SupabaseMemberInvitationRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def issue(
        self,
        *,
        bearer_token: str,
        tenant_id: UUID,
        invited_by: UUID,
        email: str,
        role: MemberRole,
        token_hash: str,
        expires_at: datetime,
    ) -> MemberInvitationRecord:
        client = authenticated_client(self._settings, bearer_token)
        payload = {
            "tenant_id": str(tenant_id),
            "email": email,
            "role": role.value,
            "token_hash": token_hash,
            "invited_by": str(invited_by),
            "expires_at": expires_at.isoformat(),
            "status": "pending",
        }
        try:
            # `.insert(...).execute()` already returns the inserted rows. Chaining `.select()`
            # after an insert is not supported by the pinned supabase-py and raised
            # AttributeError: 'SyncQueryRequestBuilder' object has no attribute 'select'
            # — surfacing as a 500 on every invitation.
            response = client.table("member_invitation").insert(payload).execute()
        except APIError as exc:
            if _api_error_code(exc) == "23505":
                raise ConflictError(details={"reason": "pending_invitation_exists"}) from exc
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return _one_invitation(response.data)

    def list_pending(self, *, bearer_token: str) -> list[MemberInvitationRecord]:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                client.table("member_invitation")
                .select(INVITATION_COLUMNS)
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return [_invitation(row) for row in _rows(response.data)]

    def revoke(
        self,
        *,
        bearer_token: str,
        invitation_id: UUID,
    ) -> MemberInvitationRecord | None:
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = (
                # No `.select()` after `.update()`: the pinned supabase-py builder does not
                # support it, and it fails the same way `.insert(...).select(...)` did.
                client.table("member_invitation")
                .update({"status": "revoked"})
                .eq("id", str(invitation_id))
                .eq("status", "pending")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = [_invitation(row) for row in _rows(response.data)]
        return rows[0] if rows else None

    def get_by_hash(self, token_hash: str) -> MemberInvitationRecord | None:
        client = self._service_role_client()
        try:
            response = (
                client.table("member_invitation")
                .select(INVITATION_COLUMNS)
                .eq("token_hash", token_hash)
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = [_invitation(row) for row in _rows(response.data)]
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "duplicate_invitation_token"})
        return rows[0] if rows else None

    def mark_expired(self, invitation_id: UUID) -> None:
        try:
            (
                self._service_role_client()
                .table("member_invitation")
                .update({"status": "expired"})
                .eq("id", str(invitation_id))
                .eq("status", "pending")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def mark_accepted(self, invitation_id: UUID) -> None:
        try:
            (
                self._service_role_client()
                .table("member_invitation")
                .update({"status": "accepted"})
                .eq("id", str(invitation_id))
                .in_("status", ["pending", "accepted"])
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    def accept(
        self,
        *,
        bearer_token: str,
        invitation: MemberInvitationRecord,
        user_id: UUID,
        email: str,
        token_hash: str,
    ) -> Membership:
        """Turn an invitation into a membership.

        Goes through the `accept_member_invitation` RPC (migration 0009) rather than writing the
        membership directly. The invitee holds no claim for the target workspace — that is what
        being invited means — so neither the invitation nor the membership is visible to them
        under RLS. The previous implementation resolved that with a service-role client, which
        works but places an RLS bypass in a request path reachable by anyone holding a token.

        The RPC re-derives authority instead: it matches on the token hash AND the caller's own
        email, so an intercepted invitation cannot be redeemed by anyone but its addressee. It is
        idempotent, returning the membership a first acceptance created rather than failing or
        duplicating.
        """
        client = authenticated_client(self._settings, bearer_token)
        try:
            response = client.rpc(
                "accept_member_invitation",
                {
                    "p_token_hash": token_hash,
                    "p_user_id": str(user_id),
                    "p_email": email,
                },
            ).execute()
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

        membership_id = response.data
        if not membership_id:
            # Unknown, expired, revoked, or already spent by someone else. Deliberately one
            # answer for all four: which it was is itself information (FR-005).
            raise PermissionDeniedError(details={"reason": "invitation_not_acceptable"})

        membership = self.find_membership(tenant_id=invitation.tenant_id, user_id=user_id)
        if membership is None:
            raise ServiceUnavailableError(details={"reason": "membership_not_readable"})
        return membership

    def find_membership(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        # Service role: called immediately after acceptance, when the caller's token still names
        # their PREVIOUS workspace (the claim only follows on the next refresh), so the new
        # membership is not yet visible to them under RLS. Scoped to one tenant and one user id
        # that the RPC has already validated.
        client = self._service_role_client()
        try:
            response = (
                client.table("membership")
                .select(
                    "id,tenant_id,user_id,email,role,mfa_enabled,preferred_locale,"
                    "is_active_workspace,status,created_at"
                )
                .eq("tenant_id", str(tenant_id))
                .eq("user_id", str(user_id))
                .limit(2)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = [_membership(row) for row in _rows(response.data)]
        if len(rows) > 1:
            raise ServiceUnavailableError(details={"reason": "duplicate_membership"})
        return rows[0] if rows else None

    def _service_role_client(self) -> Client:
        return create_client(
            self._settings.supabase_url,
            self._settings.supabase_service_role_key.get_secret_value(),
        )


class MemberInvitationService:
    def __init__(
        self,
        repository: MemberInvitationRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or SupabaseMemberInvitationRepository(self._settings)

    def issue(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        email: str,
        role: MemberRole,
    ) -> MemberInvitation:
        token = generate_member_invitation_token()
        invitation = self._repository.issue(
            bearer_token=bearer_token,
            tenant_id=member.tenant_id,
            invited_by=member.membership_id,
            email=email,
            role=role,
            token_hash=hash_member_invitation_token(token),
            expires_at=(
                datetime.now(UTC) + timedelta(days=self._settings.member_invitation_ttl_days)
            ),
        )
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="member.invited",
                target={
                    "invitation_id": str(invitation.id),
                    "email": email,
                    "role": role.value,
                },
                outcome="success",
            ),
            bearer_token=bearer_token,
        )
        return MemberInvitation(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            token=token,
        )

    def list_pending(self, *, bearer_token: str) -> list[MemberInvitation]:
        return [
            MemberInvitation.model_validate(
                invitation.model_dump(
                    exclude={"token_hash", "tenant_id", "invited_by", "created_at"}
                )
            )
            for invitation in self._repository.list_pending(bearer_token=bearer_token)
        ]

    def revoke(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        invitation_id: UUID,
    ) -> None:
        invitation = self._repository.revoke(
            bearer_token=bearer_token,
            invitation_id=invitation_id,
        )
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action="member.invitation_revoked",
                target={"invitation_id": str(invitation_id)},
                outcome="success",
            ),
            bearer_token=bearer_token,
        )
        del invitation

    def invitation_for_token(self, token: str) -> MemberInvitationRecord:
        invitation = self._repository.get_by_hash(hash_member_invitation_token(token))
        if invitation is None:
            raise InvitationRefusedError(details={"reason": "not_found"})
        return invitation

    def require_acceptable_invitation(
        self,
        *,
        token: str,
        accepting_email: str | None = None,
    ) -> MemberInvitationRecord:
        invitation = self.invitation_for_token(token)
        self._validate_acceptance(invitation, accepting_email=accepting_email)
        return invitation

    def accept(
        self,
        *,
        bearer_token: str,
        token: str,
        user_id: UUID,
        accepting_email: str | None = None,
    ) -> Membership:
        invitation = self.invitation_for_token(token)
        self._validate_acceptance(invitation, accepting_email=accepting_email)

        if invitation.status == "accepted":
            membership = self._repository.find_membership(
                tenant_id=invitation.tenant_id,
                user_id=user_id,
            )
            if membership is None:
                raise InvitationRefusedError(details={"reason": "accepted_membership_not_found"})
            return membership
        if invitation.status != "pending":
            raise InvitationRefusedError(details={"reason": invitation.status})
        if _as_utc(invitation.expires_at) <= datetime.now(UTC):
            self._repository.mark_expired(invitation.id)
            raise InvitationRefusedError(details={"reason": "expired"})

        existing = self._repository.find_membership(
            tenant_id=invitation.tenant_id,
            user_id=user_id,
        )
        if existing is not None:
            self._repository.mark_accepted(invitation.id)
            return existing

        return self._repository.accept(
            bearer_token=bearer_token,
            invitation=invitation,
            user_id=user_id,
            email=accepting_email or invitation.email,
            token_hash=hash_member_invitation_token(token),
        )

    def _validate_acceptance(
        self,
        invitation: MemberInvitationRecord,
        *,
        accepting_email: str | None,
    ) -> None:
        if (
            accepting_email is not None
            and invitation.email.casefold() != accepting_email.casefold()
        ):
            raise InvitationRefusedError(details={"reason": "email_mismatch"})
        if invitation.status == "accepted":
            return
        if invitation.status != "pending":
            raise InvitationRefusedError(details={"reason": invitation.status})
        if _as_utc(invitation.expires_at) <= datetime.now(UTC):
            self._repository.mark_expired(invitation.id)
            raise InvitationRefusedError(details={"reason": "expired"})


def generate_member_invitation_token() -> str:
    return secrets.token_urlsafe(32)


def hash_member_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_member_invitation_service() -> MemberInvitationService:
    return MemberInvitationService()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"dependency": "database"})


def _invitation(row: dict[str, object]) -> MemberInvitationRecord:
    return MemberInvitationRecord.model_validate(row)


def _one_invitation(data: object) -> MemberInvitationRecord:
    rows = [_invitation(row) for row in _rows(data)]
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": "invitation_write_failed"})
    return rows[0]


def _membership(row: dict[str, object]) -> Membership:
    return Membership.model_validate(row)


def _one_membership(data: object) -> Membership:
    rows = [_membership(row) for row in _rows(data)]
    if len(rows) != 1:
        raise ServiceUnavailableError(details={"reason": "membership_write_failed"})
    return rows[0]


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None
