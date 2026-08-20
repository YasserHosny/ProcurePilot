from typing import Annotated

from fastapi import APIRouter, Body, Depends

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.service import AuthService, get_auth_service
from procurepilot_api.modules.members.models import (
    ActiveWorkspaceRequest,
    Me,
    MeUpdate,
    SessionResponse,
    WorkspaceList,
)
from procurepilot_api.modules.members.service import (
    MemberService,
    get_member_service,
    load_me_for_token,
    require_refresh_token,
)

router = APIRouter(tags=["members"])


@router.get("/me", response_model=Me)
def get_me(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Me:
    return load_me_for_token(settings, token, member)


@router.patch("/me", response_model=Me)
def update_me(
    payload: Annotated[MeUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> Me:
    return service.update_me(bearer_token=token, member=member, patch=payload)


@router.get("/me/workspaces", response_model=WorkspaceList)
def list_workspaces(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> WorkspaceList:
    return service.list_workspaces(bearer_token=token, member=member)


@router.put("/me/active-workspace", response_model=SessionResponse)
def switch_active_workspace(
    payload: Annotated[ActiveWorkspaceRequest, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MemberService, Depends(get_member_service)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    refresh_token = require_refresh_token(payload.refresh_token)
    service.switch_active_workspace(
        bearer_token=token, member=member, tenant_id=payload.tenant_id
    )
    return auth.reissue_session(refresh_token=refresh_token)
