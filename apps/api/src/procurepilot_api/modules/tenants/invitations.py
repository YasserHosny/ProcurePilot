from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Protocol

from procurepilot_api.errors import InvitationRefusedError
from procurepilot_api.modules.tenants.models import PlatformInvitation


class PlatformInvitationStore(Protocol):
    def get_by_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> PlatformInvitation | None:
        pass

    def mark_spent(self, invitation: PlatformInvitation) -> None:
        pass


def hash_platform_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PlatformInvitationValidator:
    def __init__(self, store: PlatformInvitationStore) -> None:
        self._store = store

    def require_valid(
        self,
        *,
        invitation_token: str,
        email: str,
        for_update: bool = False,
    ) -> PlatformInvitation:
        invitation = self._store.get_by_hash(
            hash_platform_invitation_token(invitation_token),
            for_update=for_update,
        )
        if invitation is None:
            raise InvitationRefusedError(details={"reason": "not_found"})
        if invitation.status != "pending":
            raise InvitationRefusedError(details={"reason": invitation.status})
        if _as_utc(invitation.expires_at) <= datetime.now(UTC):
            raise InvitationRefusedError(details={"reason": "expired"})
        if invitation.email.casefold() != email.casefold():
            raise InvitationRefusedError(details={"reason": "email_mismatch"})
        return invitation

    def spend(self, invitation: PlatformInvitation) -> None:
        self._store.mark_spent(invitation)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
