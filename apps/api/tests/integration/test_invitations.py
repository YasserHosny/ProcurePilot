from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, InvitationRefusedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members import invitations as invitation_module
from procurepilot_api.modules.members.invitations import (
    MemberInvitationRecord,
    MemberInvitationService,
    hash_member_invitation_token,
)
from procurepilot_api.modules.members.models import Membership
from procurepilot_api.shared.audit import AuditEventCreate

BEARER = "test-access-token"  # the caller's own token; the fake repo ignores it
TOKEN = "member-invitation-token-value-0001"
TENANT_ID = UUID("22222222-2222-2222-2222-222222222222")
OWNER_ID = UUID("33333333-3333-3333-3333-333333333333")
OWNER_USER_ID = UUID("44444444-4444-4444-4444-444444444444")
INVITEE_USER_ID = UUID("55555555-5555-5555-5555-555555555555")


class _Repository:
    def __init__(self) -> None:
        self.invitations: dict[UUID, MemberInvitationRecord] = {}
        self.memberships: dict[tuple[UUID, UUID], Membership] = {}

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
        del bearer_token
        for invitation in self.invitations.values():
            if (
                invitation.tenant_id == tenant_id
                and invitation.email.casefold() == email.casefold()
                and invitation.status == "pending"
            ):
                raise ConflictError(details={"reason": "pending_invitation_exists"})
        invitation = MemberInvitationRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=expires_at,
            status="pending",
            created_at=datetime.now(UTC),
        )
        self.invitations[invitation.id] = invitation
        return invitation

    def list_pending(self, *, bearer_token: str) -> list[MemberInvitationRecord]:
        del bearer_token
        return [
            invitation
            for invitation in self.invitations.values()
            if invitation.status == "pending"
        ]

    def revoke(
        self,
        *,
        bearer_token: str,
        invitation_id: UUID,
    ) -> MemberInvitationRecord | None:
        del bearer_token
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.status != "pending":
            return None
        updated = invitation.model_copy(update={"status": "revoked"})
        self.invitations[invitation_id] = updated
        return updated

    def get_by_hash(self, token_hash: str) -> MemberInvitationRecord | None:
        for invitation in self.invitations.values():
            if invitation.token_hash == token_hash:
                return invitation
        return None

    def mark_expired(self, invitation_id: UUID) -> None:
        invitation = self.invitations[invitation_id]
        self.invitations[invitation_id] = invitation.model_copy(update={"status": "expired"})

    def mark_accepted(self, invitation_id: UUID) -> None:
        invitation = self.invitations[invitation_id]
        self.invitations[invitation_id] = invitation.model_copy(update={"status": "accepted"})

    def accept(
        self,
        *,
        bearer_token: str,
        invitation: MemberInvitationRecord,
        user_id: UUID,
        email: str,
        token_hash: str,
    ) -> Membership:
        del bearer_token, email, token_hash  # the real repository forwards these to the RPC
        existing = self.find_membership(tenant_id=invitation.tenant_id, user_id=user_id)
        if existing is not None:
            self.mark_accepted(invitation.id)
            return existing
        membership = Membership(
            id=uuid4(),
            tenant_id=invitation.tenant_id,
            user_id=user_id,
            email=invitation.email,
            role=invitation.role,
            mfa_enabled=False,
            preferred_locale=None,
            is_active_workspace=True,
            status="active",
            created_at=datetime.now(UTC),
        )
        self.memberships[(invitation.tenant_id, user_id)] = membership
        self.mark_accepted(invitation.id)
        return membership

    def find_membership(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        return self.memberships.get((tenant_id, user_id))


class _AuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventCreate] = []

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        assert bearer_token == "owner-token"
        self.events.append(event)


@pytest.fixture
def repository() -> _Repository:
    return _Repository()


@pytest.fixture
def service(
    repository: _Repository,
    monkeypatch: pytest.MonkeyPatch,
) -> MemberInvitationService:
    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    return MemberInvitationService(repository=repository, settings=get_settings())


def test_issue_invitation_hashes_token_and_sets_ttl(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    invitation = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )

    stored = repository.invitations[invitation.id]
    assert invitation.token is not None
    assert stored.token_hash == hash_member_invitation_token(invitation.token)
    assert stored.token_hash != invitation.token
    assert stored.status == "pending"
    assert 6 <= (stored.expires_at - datetime.now(UTC)).days <= 7


def test_accept_invitation_creates_membership(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    _add_invitation(repository)

    membership = service.accept(bearer_token=BEARER, token=TOKEN,
        user_id=INVITEE_USER_ID,
        accepting_email="buyer@example.test",
    )

    assert membership.tenant_id == TENANT_ID
    assert membership.user_id == INVITEE_USER_ID
    assert membership.email == "buyer@example.test"
    assert membership.role == MemberRole.buyer
    assert repository.get_by_hash(hash_member_invitation_token(TOKEN)).status == "accepted"


def test_double_accept_returns_existing_membership_without_creating_a_second_one(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    _add_invitation(repository)

    first = service.accept(bearer_token=BEARER, token=TOKEN,
        user_id=INVITEE_USER_ID,
        accepting_email="buyer@example.test",
    )
    second = service.accept(bearer_token=BEARER, token=TOKEN,
        user_id=INVITEE_USER_ID,
        accepting_email="buyer@example.test",
    )

    assert second.id == first.id
    assert list(repository.memberships.values()) == [first]


def test_accept_refuses_expired_invitation(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    invitation_id = _add_invitation(
        repository,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(InvitationRefusedError) as exc:
        service.accept(
            bearer_token=BEARER,
            token=TOKEN,
            user_id=INVITEE_USER_ID,
            accepting_email="buyer@example.test",
        )

    assert exc.value.details == {"reason": "expired"}
    assert repository.invitations[invitation_id].status == "expired"
    assert repository.memberships == {}


def test_accept_refuses_revoked_invitation(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    _add_invitation(repository, status="revoked")

    with pytest.raises(InvitationRefusedError) as exc:
        service.accept(
            bearer_token=BEARER,
            token=TOKEN,
            user_id=INVITEE_USER_ID,
            accepting_email="buyer@example.test",
        )

    assert exc.value.details == {"reason": "revoked"}
    assert repository.memberships == {}


def test_accept_refuses_wrong_email(
    service: MemberInvitationService,
    repository: _Repository,
) -> None:
    _add_invitation(repository)

    with pytest.raises(InvitationRefusedError) as exc:
        service.accept(
            bearer_token=BEARER,
            token=TOKEN,
            user_id=INVITEE_USER_ID,
            accepting_email="other@example.test",
        )

    assert exc.value.details == {"reason": "email_mismatch"}
    assert repository.memberships == {}


def test_one_pending_invitation_per_address_per_workspace(
    service: MemberInvitationService,
) -> None:
    service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="Buyer@Example.Test",
        role=MemberRole.buyer,
    )

    with pytest.raises(ConflictError) as exc:
        service.issue(
            bearer_token="owner-token",
            member=_owner(),
            email="buyer@example.test",
            role=MemberRole.viewer,
        )

    assert exc.value.details == {"reason": "pending_invitation_exists"}


def _owner() -> CurrentMember:
    return CurrentMember(
        membership_id=OWNER_ID,
        tenant_id=TENANT_ID,
        user_id=OWNER_USER_ID,
        email="owner@example.test",
        role=MemberRole.owner,
    )


def _add_invitation(
    repository: _Repository,
    *,
    status: str = "pending",
    expires_at: datetime | None = None,
) -> UUID:
    invitation = MemberInvitationRecord(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email="buyer@example.test",
        role=MemberRole.buyer,
        token_hash=hash_member_invitation_token(TOKEN),
        invited_by=OWNER_ID,
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
        status=status,
        created_at=datetime.now(UTC),
    )
    repository.invitations[invitation.id] = invitation
    return invitation.id
