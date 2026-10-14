from typing import Annotated

from fastapi import APIRouter, Body, Depends

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.members.models import SessionResponse
from procurepilot_api.modules.members.service import authenticated_client, load_me_for_token
from procurepilot_api.modules.tenants.models import (
    ConfigOptions,
    SignupRequest,
    Tenant,
    TenantUpdate,
)
from procurepilot_api.modules.tenants.service import (
    TenantSignupRepository,
    TenantSignupService,
    get_tenant_signup_repository,
    get_tenant_signup_service,
)

router = APIRouter(tags=["tenants"])


@router.post("/auth/signup", status_code=201, response_model=SessionResponse)
def signup(
    payload: Annotated[SignupRequest, Body()],
    service: Annotated[TenantSignupService, Depends(get_tenant_signup_service)],
) -> SessionResponse:
    return service.signup(payload)


@router.get("/reference/config-options", response_model=ConfigOptions)
def config_options(
    repository: Annotated[TenantSignupRepository, Depends(get_tenant_signup_repository)],
) -> ConfigOptions:
    return repository.config_options()


@router.get("/tenant", response_model=Tenant)
def get_tenant(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Tenant:
    return load_me_for_token(settings=settings, bearer_token=token, member=member).tenant


@router.patch("/tenant", response_model=Tenant)
def update_tenant(
    payload: Annotated[TenantUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Tenant:
    update = payload.model_dump(exclude_none=True)
    if update:
        client = authenticated_client(settings, token)
        previous_currency: str | None = None
        if "currency" in update:
            # The home currency drives form defaults and the extraction fallback, so it must be
            # a currency the product supports (same reference table sign-up validates against).
            supported = (
                client.table("supported_currency")
                .select("code")
                .eq("code", update["currency"])
                .eq("is_enabled", True)
                .limit(1)
                .execute()
            )
            if not supported.data:
                raise UnprocessableEntityError(details={"currency": "unsupported"})
            current = (
                client.table("tenant")
                .select("currency")
                .eq("id", str(member.tenant_id))
                .limit(1)
                .execute()
            )
            previous_currency = current.data[0]["currency"] if current.data else None
        client.table("tenant").update(update).eq("id", str(member.tenant_id)).execute()
        if "currency" in update and previous_currency != update["currency"]:
            client.rpc(
                "record_audit_event",
                {
                    "p_action": "tenant.currency_changed",
                    "p_outcome": "success",
                    "p_tenant_id": str(member.tenant_id),
                    "p_actor_membership_id": str(member.membership_id),
                    "p_actor_email": member.email,
                    "p_target": {"from": previous_currency, "to": update["currency"]},
                },
            ).execute()
    return load_me_for_token(settings=settings, bearer_token=token, member=member).tenant
