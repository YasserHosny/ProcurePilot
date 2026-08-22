from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.organisation.schemas import (
    Branch,
    BranchCreate,
    BranchList,
    BranchUpdate,
)
from procurepilot_api.modules.organisation.service import (
    OrganisationService,
    get_organisation_service,
)

router = APIRouter(tags=["organisation"])


@router.get("/organisation/branches", response_model=BranchList)
def list_branches(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
    is_active: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> BranchList:
    return service.list_branches(
        bearer_token=token,
        is_active=is_active,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/organisation/branches",
    status_code=status.HTTP_201_CREATED,
    response_model=Branch,
)
def create_branch(
    payload: Annotated[BranchCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Branch:
    return service.create_branch(bearer_token=token, member=member, payload=payload)


@router.patch("/organisation/branches/{branch_id}", response_model=Branch)
def update_branch(
    branch_id: UUID,
    payload: Annotated[BranchUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[OrganisationService, Depends(get_organisation_service)],
) -> Branch:
    return service.update_branch(
        bearer_token=token,
        member=member,
        branch_id=branch_id,
        patch=payload,
    )
