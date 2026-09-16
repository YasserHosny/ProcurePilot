from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import InvalidCredentialsError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.auth.service import AuthService, get_auth_service
from procurepilot_api.modules.digests.service import DigestsService
from procurepilot_api.modules.members.invitations import (
    MemberInvitationService,
    get_member_invitation_service,
)
from procurepilot_api.modules.members.models import (
    ActiveWorkspaceRequest,
    Me,
    Member,
    MemberInvitation,
    MemberInvitationAccept,
    MemberInvitationCreate,
    MemberInvitationList,
    MemberList,
    MemberRoleUpdate,
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
from procurepilot_api.modules.organisation.schemas import (
    BranchRoleAssignment,
    BranchRoleAssignmentCreate,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer

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


@router.get("/members", response_model=MemberList)
def list_members(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberService, Depends(get_member_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> MemberList:
    return service.list_members(bearer_token=token, cursor=cursor, limit=limit)


@router.patch("/members/{member_id}", response_model=Member)
def update_member_role(
    member_id: UUID,
    payload: Annotated[MemberRoleUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> Member:
    return service.update_member_role(
        bearer_token=token,
        actor=member,
        member_id=member_id,
        patch=payload,
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> Response:
    service.remove_member(bearer_token=token, actor=member, member_id=member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/organisation/branch-role-assignments",
    status_code=status.HTTP_201_CREATED,
    response_model=BranchRoleAssignment,
)
def create_branch_role_assignment(
    payload: Annotated[BranchRoleAssignmentCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> BranchRoleAssignment:
    return service.create_branch_role_assignment(
        bearer_token=token,
        actor=member,
        payload=payload,
    )


@router.delete(
    "/organisation/branch-role-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_branch_role_assignment(
    assignment_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberService, Depends(get_member_service)],
) -> Response:
    service.remove_branch_role_assignment(
        bearer_token=token,
        actor=member,
        assignment_id=assignment_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/invitations",
    response_model=MemberInvitationList,
    response_model_exclude_none=True,
)
def list_invitations(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberInvitationService, Depends(get_member_invitation_service)],
) -> MemberInvitationList:
    return MemberInvitationList(items=service.list_pending(bearer_token=token))


@router.post("/invitations", status_code=status.HTTP_201_CREATED, response_model=MemberInvitation)
def issue_invitation(
    payload: Annotated[MemberInvitationCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberInvitationService, Depends(get_member_invitation_service)],
) -> MemberInvitation:
    return service.issue(
        bearer_token=token,
        member=member,
        email=payload.email,
        role=payload.role,
    )


@router.post("/invitations/accept", response_model=SessionResponse)
def accept_invitation(
    payload: Annotated[MemberInvitationAccept, Body()],
    invitation_service: Annotated[
        MemberInvitationService,
        Depends(get_member_invitation_service),
    ],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    invitation = invitation_service.require_acceptable_invitation(token=payload.token)
    if payload.password is None:
        raise UnprocessableEntityError(details={"password": "required_to_issue_session"})

    try:
        user_id = auth.create_auth_user(email=invitation.email, password=payload.password)
    except InvalidCredentialsError:
        existing_session = auth.login(email=invitation.email, password=payload.password)
        user_id = existing_session.user.id

    # Accept FIRST, then sign in. Signing in builds a session that requires a tenant_id claim,
    # and the auth hook only injects that once a membership exists — which acceptance is what
    # creates. Signing in first made acceptance depend on its own outcome.
    membership = invitation_service.accept(
        bearer_token="",
        token=payload.token,
        user_id=user_id,
        accepting_email=invitation.email,
    )
    session = auth.login(email=invitation.email, password=payload.password)
    try:
        DigestsService().provision_default_subscription(
            tenant_id=membership.tenant_id,
            membership_id=membership.id,
            email=membership.email,
            bearer_token=session.access_token,
        )
    except Exception:
        # Advisory provisioning failure must not roll back invitation acceptance
        pass
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=membership.tenant_id,
            actor_membership_id=membership.id,
            actor_email=membership.email,
            action="member.invitation_accepted",
            target={"invitation_id": str(invitation.id)},
            outcome="success",
        ),
        bearer_token=session.access_token,
    )
    return session


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[MemberInvitationService, Depends(get_member_invitation_service)],
) -> Response:
    service.revoke(bearer_token=token, member=member, invitation_id=invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
