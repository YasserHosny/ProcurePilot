from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.landed_cost.schemas import LandedCost
from procurepilot_api.modules.landed_cost.service import LandedCostService, get_landed_cost_service

router = APIRouter(tags=["landed_cost"])


@router.get("/quotation-lines/{line_id}/landed-cost", response_model=LandedCost)
def get_landed_cost(
    line_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[LandedCostService, Depends(get_landed_cost_service)],
) -> LandedCost:
    return service.get_landed_cost(bearer_token=token, line_id=line_id)
