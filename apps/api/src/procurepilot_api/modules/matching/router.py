from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query
from pydantic import BaseModel

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.matching.resolution_service import (
    MatchResolutionService,
    get_match_resolution_service,
)
from procurepilot_api.modules.matching.schemas import (
    BulkConfirmResult,
    ExactMatchSummary,
    MatchDecision,
    MatchQueueList,
    MatchResolutionRequest,
    MatchTask,
    MatchTaskPriority,
    MatchTaskReason,
    MatchTaskStatusFilter,
    QuotationMatches,
)
from procurepilot_api.modules.matching.service import MatchingService, get_matching_service

router = APIRouter(tags=["matching"])


class NextMatchTask(BaseModel):
    next_task_id: UUID | None
    next_quotation_line_id: UUID | None


@router.get("/match-tasks/next", response_model=NextMatchTask)
def next_match_task(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
    exclude_task_id: UUID | None = None,
) -> NextMatchTask:
    queue = service.list_match_tasks(
        bearer_token=token,
        member=member,
        limit=100,
        status="open",
        sort_by="created_at",
        sort_order="desc",
    )
    items = getattr(queue, "items", [])
    next_item = next((item for item in items if item.id != exclude_task_id), None)
    return NextMatchTask(
        next_task_id=next_item.id if next_item else None,
        next_quotation_line_id=next_item.quotation_line.id if next_item else None,
    )


WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.get("/quotation-lines/{line_id}/match-task", response_model=MatchTask)
def match_task_for_line(
    line_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> MatchTask:
    return service.match_task_for_line(bearer_token=token, line_id=line_id)


@router.get("/quotations/{quotation_id}/matches", response_model=QuotationMatches)
def quotation_matches(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> QuotationMatches:
    return service.quotation_matches(bearer_token=token, member=member, quotation_id=quotation_id)


@router.get("/match-tasks", response_model=MatchQueueList)
def list_match_tasks(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
    status: Annotated[MatchTaskStatusFilter, Query()] = "open",
    priority: Annotated[MatchTaskPriority | None, Query()] = None,
    reason: Annotated[MatchTaskReason | None, Query()] = None,
    quotation_id: Annotated[UUID | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    sort_by: Annotated[Literal["created_at", "priority", "status"], Query()] = "created_at",
    sort_order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> MatchQueueList:
    return service.list_match_tasks(
        bearer_token=token,
        member=member,
        cursor=cursor,
        limit=limit,
        status=status,
        priority=priority,
        reason=reason,
        quotation_id=quotation_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/quotation-lines/{line_id}/match", response_model=MatchDecision)
def resolve_match(
    line_id: UUID,
    payload: Annotated[MatchResolutionRequest, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[MatchResolutionService, Depends(get_match_resolution_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> MatchDecision:
    return service.resolve(
        bearer_token=token,
        member=member,
        line_id=line_id,
        payload=payload,
        idempotency_key=_idempotency_key,
    )


@router.get("/match-tasks/exact-matches", response_model=ExactMatchSummary)
def count_exact_matches(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[MatchResolutionService, Depends(get_match_resolution_service)],
) -> ExactMatchSummary:
    return service.count_exact_matches(bearer_token=token)


@router.post("/match-tasks/confirm-exact", response_model=BulkConfirmResult)
def confirm_exact_matches(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[MatchResolutionService, Depends(get_match_resolution_service)],
) -> BulkConfirmResult:
    return service.confirm_exact_matches(bearer_token=token, member=member)
