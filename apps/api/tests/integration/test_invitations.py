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

    locale = "en"

    def workspace_for_email(self, *, bearer_token: str, tenant_id: UUID) -> tuple[str, str]:
        assert bearer_token == "owner-token"
        assert tenant_id == TENANT_ID
        return "Example Workspace", self.locale

    def rotate_token(
        self,
        *,
        bearer_token: str,
        invitation_id: UUID,
        token_hash: str,
        expires_at: datetime,
        rotated_before: datetime | None = None,
    ) -> MemberInvitationRecord | None:
        assert bearer_token == "owner-token"
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.status != "pending":
            return None
        if rotated_before is not None and invitation.expires_at > rotated_before:
            return None
        updated = invitation.model_copy(update={"token_hash": token_hash, "expires_at": expires_at})
        self.invitations[invitation_id] = updated
        return updated

    def get_pending(
        self, *, bearer_token: str, invitation_id: UUID
    ) -> MemberInvitationRecord | None:
        assert bearer_token == "owner-token"
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.status != "pending":
            return None
        return invitation

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
            invitation for invitation in self.invitations.values() if invitation.status == "pending"
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
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")
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

    membership = service.accept(
        bearer_token=BEARER,
        token=TOKEN,
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

    first = service.accept(
        bearer_token=BEARER,
        token=TOKEN,
        user_id=INVITEE_USER_ID,
        accepting_email="buyer@example.test",
    )
    second = service.accept(
        bearer_token=BEARER,
        token=TOKEN,
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


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_issue_emails_invitation(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch, locale: str
) -> None:
    from procurepilot_api.shared.i18n import t
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    repository.locale = locale
    FakeMailer.clear()
    mailer = FakeMailer()
    settings = get_settings().model_copy(update={"web_origin": "https://app.example.test/"})
    service = MemberInvitationService(repository=repository, settings=settings, mailer=mailer)
    result = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    assert result.email_delivery == "sent"
    assert len(mailer.sent_messages) == 1
    message = mailer.sent_messages[0]
    assert message.to == "buyer@example.test"
    for content in (message.body, message.html):
        assert "Example Workspace" in content
        assert _owner().email in content
        assert (
            f"https://app.example.test/onboarding/accept-invitation?token={result.token}" in content
        )
    assert f'lang="{locale}"' in message.html
    assert f'dir="{"rtl" if locale == "ar" else "ltr"}"' in message.html
    assert message.subject == t(
        "team.invitationEmail.subject", locale, workspace="Example Workspace"
    )
    event = audit.events[-1]
    assert event.action == "member.invitation_emailed"
    assert event.target["delivery"] == "sent"
    assert event.outcome == "success"
    for event in audit.events:
        assert result.token not in str(event.target)
        assert hash_member_invitation_token(result.token) not in str(event.target)


def test_issue_without_config_still_returns_token(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    monkeypatch.setenv("RFQ_MAILER_MODE", "stub")
    service = MemberInvitationService(repository=repository, settings=get_settings())
    result = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    assert result.token
    assert result.email_delivery == "not_configured"
    assert audit.events[-1].outcome == "refused"
    assert audit.events[-1].target["delivery"] == "not_configured"


@pytest.mark.parametrize("failure", ["provider", "lookup", "render"])
def test_email_failure_does_not_lose_invitation(
    repository: _Repository,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("sensitive exception text must not be logged")

    mailer = FakeMailer()
    if failure == "provider":
        monkeypatch.setattr(mailer, "send", fail)
    elif failure == "lookup":
        monkeypatch.setattr(repository, "workspace_for_email", fail)
    else:
        monkeypatch.setattr(invitation_module, "render_invitation_email", fail)
    service = MemberInvitationService(repository=repository, settings=get_settings(), mailer=mailer)
    result = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    assert result.token
    assert result.email_delivery == "failed"
    assert audit.events[-1].outcome == "refused"
    assert audit.events[-1].target["delivery"] == "failed"
    assert result.token not in caplog.text
    assert hash_member_invitation_token(result.token) not in caplog.text
    assert "sensitive exception text" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_resend_rotates_same_row_and_invalidates_old_token(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    invitation_id = _add_invitation(repository)
    before = repository.invitations[invitation_id]
    FakeMailer.clear()
    mailer = FakeMailer()
    service = MemberInvitationService(repository=repository, settings=get_settings(), mailer=mailer)
    result = service.resend(
        bearer_token="owner-token", member=_owner(), invitation_id=invitation_id
    )
    assert result.id == invitation_id
    assert result.token != TOKEN
    assert result.expires_at > before.expires_at
    assert repository.invitations[invitation_id].token_hash != before.token_hash
    assert service.invitation_for_token(result.token).id == invitation_id
    with pytest.raises(InvitationRefusedError):
        service.invitation_for_token(TOKEN)
    assert result.email_delivery == "sent"
    assert len(mailer.sent_messages) == 1
    assert audit.events[-2].action == "member.invitation_resent"
    assert audit.events[-1].target["resend"] is True
    for event in audit.events:
        assert result.token not in str(event.target)
        assert hash_member_invitation_token(result.token) not in str(event.target)


@pytest.mark.parametrize("status", ["unknown", "accepted", "revoked", "expired"])
def test_resend_missing_or_nonpending_is_not_found(
    service: MemberInvitationService, repository: _Repository, status: str
) -> None:
    from procurepilot_api.errors import NotFoundError

    invitation_id = uuid4() if status == "unknown" else _add_invitation(repository, status=status)
    with pytest.raises(NotFoundError):
        service.resend(bearer_token="owner-token", member=_owner(), invitation_id=invitation_id)


def test_resend_immediately_after_issue_raises_conflict(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    FakeMailer.clear()
    mailer = FakeMailer()
    service = MemberInvitationService(repository=repository, settings=get_settings(), mailer=mailer)

    invitation = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    initial_hash = repository.invitations[invitation.id].token_hash
    assert len(mailer.sent_messages) == 1
    events_count_before = len(audit.events)

    with pytest.raises(ConflictError) as exc_info:
        service.resend(bearer_token="owner-token", member=_owner(), invitation_id=invitation.id)

    assert exc_info.value.details is not None
    assert exc_info.value.details["reason"] == "resent_recently"
    assert 1 <= exc_info.value.details["retry_after_seconds"] <= 60
    assert repository.invitations[invitation.id].token_hash == initial_hash
    assert len(mailer.sent_messages) == 1
    assert len(audit.events) == events_count_before
    assert not any(event.action == "member.invitation_resent" for event in audit.events)
    assert [event.action for event in audit.events].count("member.invitation_emailed") == 1


def test_resend_when_older_than_cooldown_rotates_and_emails(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    invitation_id = _add_invitation(
        repository,
        expires_at=datetime.now(UTC) + timedelta(days=7) - timedelta(seconds=120),
    )
    before = repository.invitations[invitation_id]
    FakeMailer.clear()
    mailer = FakeMailer()
    service = MemberInvitationService(repository=repository, settings=get_settings(), mailer=mailer)

    result = service.resend(
        bearer_token="owner-token", member=_owner(), invitation_id=invitation_id
    )
    assert result.id == invitation_id
    assert result.token != TOKEN
    assert result.expires_at > before.expires_at
    assert repository.invitations[invitation_id].token_hash != before.token_hash
    assert result.email_delivery == "sent"
    assert len(mailer.sent_messages) == 1
    assert audit.events[-2].action == "member.invitation_resent"


def test_two_resends_back_to_back_after_cooldown(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    invitation_id = _add_invitation(
        repository,
        expires_at=datetime.now(UTC) + timedelta(days=7) - timedelta(seconds=120),
    )
    FakeMailer.clear()
    mailer = FakeMailer()
    service = MemberInvitationService(repository=repository, settings=get_settings(), mailer=mailer)

    first_resend = service.resend(
        bearer_token="owner-token", member=_owner(), invitation_id=invitation_id
    )
    assert len(mailer.sent_messages) == 1
    assert service.invitation_for_token(first_resend.token).id == invitation_id

    with pytest.raises(ConflictError) as exc_info:
        service.resend(bearer_token="owner-token", member=_owner(), invitation_id=invitation_id)

    assert exc_info.value.details is not None
    assert exc_info.value.details["reason"] == "resent_recently"
    assert 1 <= exc_info.value.details["retry_after_seconds"] <= 60
    assert len(mailer.sent_messages) == 1
    assert service.invitation_for_token(first_resend.token).id == invitation_id


def test_resend_immediate_succeeds_when_cooldown_zero(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    settings = get_settings().model_copy(update={"member_invitation_resend_cooldown_seconds": 0})
    FakeMailer.clear()
    mailer = FakeMailer()
    service = MemberInvitationService(repository=repository, settings=settings, mailer=mailer)

    invitation = service.issue(
        bearer_token="owner-token",
        member=_owner(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    assert len(mailer.sent_messages) == 1

    result = service.resend(
        bearer_token="owner-token", member=_owner(), invitation_id=invitation.id
    )
    assert result.id == invitation.id
    assert len(mailer.sent_messages) == 2


def test_resend_of_time_expired_pending_invitation_is_not_blocked_by_cooldown(
    repository: _Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.mailer import FakeMailer

    audit = _AuditWriter()
    monkeypatch.setattr(invitation_module, "get_audit_writer", lambda: audit)
    past_expiry = datetime.now(UTC) - timedelta(days=1)
    invitation_id = _add_invitation(
        repository,
        status="pending",
        expires_at=past_expiry,
    )
    before = repository.invitations[invitation_id]
    FakeMailer.clear()
    mailer = FakeMailer()
    settings = get_settings()
    assert settings.member_invitation_resend_cooldown_seconds == 60
    service = MemberInvitationService(repository=repository, settings=settings, mailer=mailer)

    now = datetime.now(UTC)
    result = service.resend(
        bearer_token="owner-token", member=_owner(), invitation_id=invitation_id
    )

    assert result.id == invitation_id
    assert result.token != TOKEN
    assert repository.invitations[invitation_id].token_hash != before.token_hash
    expected_expiry = now + timedelta(days=settings.member_invitation_ttl_days)
    assert abs((result.expires_at - expected_expiry).total_seconds()) < 5
    assert repository.invitations[invitation_id].expires_at == result.expires_at
    assert result.email_delivery == "sent"
    assert len(mailer.sent_messages) == 1
    assert mailer.sent_messages[0].to == "buyer@example.test"
