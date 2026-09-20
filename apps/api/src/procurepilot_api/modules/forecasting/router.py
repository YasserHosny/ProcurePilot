from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.forecasting.schemas import (
    PrepareRequestInput,
    PrepareRequestResponse,
    RecomputeResponse,
    ReorderProposalList,
)
from procurepilot_api.modules.forecasting.service import (
    ForecastingService,
    get_forecasting_service,
)

router = APIRouter(prefix="/forecasting", tags=["forecasting"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post(
    "/recompute",
    status_code=status.HTTP_200_OK,
    response_model=RecomputeResponse,
    operation_id="recomputeForecasts",
)
def recompute_forecasts(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ForecastingService, Depends(get_forecasting_service)],
) -> RecomputeResponse:
    return service.recompute(bearer_token=token, member=member)


@router.get(
    "/reorder-proposals",
    response_model=ReorderProposalList,
    operation_id="listReorderProposals",
)
def list_reorder_proposals(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ForecastingService, Depends(get_forecasting_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> ReorderProposalList:
    return service.list_proposals(bearer_token=token, cursor=cursor, limit=limit)


@router.post(
    "/reorder-proposals/{proposal_id}/prepare-request",
    response_model=PrepareRequestResponse,
    operation_id="prepareReorderRequest",
)
def prepare_reorder_request(
    proposal_id: UUID,
    payload: Annotated[PrepareRequestInput, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ForecastingService, Depends(get_forecasting_service)],
) -> PrepareRequestResponse:
    return service.prepare_request(
        bearer_token=token,
        member=member,
        proposal_id=proposal_id,
        payload=payload,
    )
