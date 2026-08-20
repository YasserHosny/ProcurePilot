from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from procurepilot_api.errors import (
    InvitationRefusedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members.models import Me, SessionResponse
from procurepilot_api.modules.tenants.invitations import (
    PlatformInvitationValidator,
    hash_platform_invitation_token,
)
from procurepilot_api.modules.tenants.models import (
    PlatformInvitation,
    SignupRequest,
    Tenant,
    WorkspaceCreated,
)
from procurepilot_api.modules.tenants.service import TenantSignupService

TOKEN = "a" * 32
EMAIL = "owner@example.test"
USER_ID = UUID("11111111-1111-1111-1111-111111111111")


class _InvitationStore:
    def __init__(self, invitation: PlatformInvitation | None) -> None:
        self.invitation = invitation

    def get_by_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> PlatformInvitation | None:
        if self.invitation is None or self.invitation.token_hash != token_hash:
            return None
        return self.invitation

    def mark_spent(self, invitation: PlatformInvitation) -> None:
        invitation.status = "spent"
        invitation.spent_at = datetime.now(UTC)


class _Repository:
    def __init__(
        self,
        invitation: PlatformInvitation | None,
        *,
        supported_currency: bool = True,
        fail_after_tenant: bool = False,
    ) -> None:
        self.store = _InvitationStore(invitation)
        self.supported_currency = supported_currency
        self.fail_after_tenant = fail_after_tenant
        self.tenants: list[Tenant] = []

    def prevalidate(self, request: SignupRequest) -> None:
        self._validate(request)

    def create_workspace(self, request: SignupRequest, user_id: UUID) -> WorkspaceCreated:
        snapshot = list(self.tenants)
        try:
            PlatformInvitationValidator(self.store).require_valid(
                invitation_token=request.invitation_token,
                email=request.email,
                for_update=True,
            )
            self._validate_config(request)
            tenant = Tenant(
                id=uuid4(),
                name=request.business_name,
                slug="acme-supplies",
                region=request.region,
                currency=request.currency,
                tax_model=request.tax_model,
                default_locale=request.default_locale,
                created_at=datetime.now(UTC),
            )
            self.tenants.append(tenant)
            if self.fail_after_tenant:
                raise ServiceUnavailableError(details={"reason": "simulated_insert_failure"})
            if self.store.invitation is not None:
                self.store.mark_spent(self.store.invitation)
            return WorkspaceCreated(
                tenant=tenant,
                membership_id=uuid4(),
                user_id=user_id,
                email=request.email,
                role=MemberRole.owner,
            )
        except Exception:
            self.tenants = snapshot
            raise

    def _validate(self, request: SignupRequest) -> None:
        PlatformInvitationValidator(self.store).require_valid(
            invitation_token=request.invitation_token,
            email=request.email,
        )
        self._validate_config(request)

    def _validate_config(self, request: SignupRequest) -> None:
        if not self.supported_currency or request.currency != "GBP":
            raise UnprocessableEntityError(details={"currency": "unsupported"})


class _Auth:
    def __init__(self) -> None:
        self.created_users: list[str] = []

    def create_auth_user(self, *, email: str, password: str) -> UUID:
        self.created_users.append(email)
        return USER_ID

    def login(self, *, email: str, password: str) -> SessionResponse:
        tenant = Tenant(
            id=uuid4(),
            name="Acme Supplies",
            slug="acme-supplies",
            region="GB",
            currency="GBP",
            tax_model="uk_vat_standard",
            default_locale="en",
        )
        return SessionResponse(
            access_token="access",
            refresh_token="refresh",
            expires_in=3600,
            user=Me(
                id=USER_ID,
                email=email,
                role=MemberRole.owner,
                preferred_locale=None,
                mfa_enabled=False,
                tenant=tenant,
            ),
        )


def _request(currency: str = "GBP") -> SignupRequest:
    return SignupRequest(
        invitation_token=TOKEN,
        email=EMAIL,
        password="correct-horse-password",
        business_name="Acme Supplies",
        region="GB",
        currency=currency,
        tax_model="uk_vat_standard",
        default_locale="en",
    )


def _invitation(
    *,
    status: str = "pending",
    expires_at: datetime | None = None,
) -> PlatformInvitation:
    return PlatformInvitation(
        id=uuid4(),
        email=EMAIL,
        token_hash=hash_platform_invitation_token(TOKEN),
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
        status=status,
    )


def test_valid_invitation_creates_workspace_and_spends_invitation() -> None:
    repo = _Repository(_invitation())
    auth = _Auth()
    response = TenantSignupService(repository=repo, auth_service=auth).signup(_request())

    assert response.access_token == "access"
    assert len(repo.tenants) == 1
    assert repo.store.invitation is not None
    assert repo.store.invitation.status == "spent"
    assert auth.created_users == [EMAIL]


@pytest.mark.parametrize(
    ("invitation", "reason"),
    [
        (_invitation(expires_at=datetime.now(UTC) - timedelta(seconds=1)), "expired"),
        (_invitation(status="spent"), "spent"),
        (_invitation(status="revoked"), "revoked"),
        (None, "not_found"),
    ],
)
def test_refuses_invalid_invitations(
    invitation: PlatformInvitation | None,
    reason: str,
) -> None:
    repo = _Repository(invitation)
    auth = _Auth()

    with pytest.raises(InvitationRefusedError) as exc:
        TenantSignupService(repository=repo, auth_service=auth).signup(_request())

    assert exc.value.details == {"reason": reason}
    assert repo.tenants == []
    assert auth.created_users == []


def test_refuses_unsupported_currency_before_creating_user_or_tenant() -> None:
    repo = _Repository(_invitation(), supported_currency=False)
    auth = _Auth()

    with pytest.raises(UnprocessableEntityError):
        TenantSignupService(repository=repo, auth_service=auth).signup(_request(currency="USD"))

    assert repo.tenants == []
    assert auth.created_users == []


def test_failed_signup_leaves_no_partial_tenant() -> None:
    repo = _Repository(_invitation(), fail_after_tenant=True)

    with pytest.raises(ServiceUnavailableError):
        TenantSignupService(repository=repo, auth_service=_Auth()).signup(_request())

    assert repo.tenants == []
