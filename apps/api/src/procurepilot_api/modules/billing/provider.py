from __future__ import annotations

from typing import Protocol
from uuid import UUID

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.billing.schemas import BillingAccount, LimitCheck
from procurepilot_api.modules.billing.service import BillingService


class BillingProvider(Protocol):
    def assign_default_plan(self, tenant_id: UUID) -> BillingAccount: ...

    def current_account(self, tenant_id: UUID) -> BillingAccount: ...

    def check_limit(self, tenant_id: UUID, resource: str) -> LimitCheck: ...


class StubBillingProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._service = BillingService(self._settings)

    def assign_default_plan(self, tenant_id: UUID) -> BillingAccount:
        member = CurrentMember(
            membership_id=UUID("00000000-0000-0000-0000-000000000000"),
            tenant_id=tenant_id,
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            email="billing-stub@procurepilot.local",
            role=MemberRole.owner,
        )
        return self._service.assign_default_plan(member=member)

    def current_account(self, tenant_id: UUID) -> BillingAccount:
        member = CurrentMember(
            membership_id=UUID("00000000-0000-0000-0000-000000000000"),
            tenant_id=tenant_id,
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            email="billing-stub@procurepilot.local",
            role=MemberRole.owner,
        )
        return self._service.current_account(member=member)

    def check_limit(self, tenant_id: UUID, resource: str) -> LimitCheck:
        member = CurrentMember(
            membership_id=UUID("00000000-0000-0000-0000-000000000000"),
            tenant_id=tenant_id,
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            email="billing-stub@procurepilot.local",
            role=MemberRole.owner,
        )
        return self._service.check_limit(member=member, resource=resource)


def get_billing_provider() -> BillingProvider:
    return StubBillingProvider()
