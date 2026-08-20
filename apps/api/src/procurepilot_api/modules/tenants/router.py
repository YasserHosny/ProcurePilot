from typing import Annotated

from fastapi import APIRouter, Body, Depends

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
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
        authenticated_client(settings, token).table("tenant").update(update).eq(
            "id", str(member.tenant_id)
        ).execute()
    return load_me_for_token(settings=settings, bearer_token=token, member=member).tenant
