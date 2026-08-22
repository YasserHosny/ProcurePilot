from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.modules.alerts.schemas import AlertDismissal, AlertList
from procurepilot_api.modules.alerts.service import AlertService, get_alert_service
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

router = APIRouter(tags=["alerts"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)
AlertKindParam = Literal[
    "recommended_price_expiring",
    "preferred_supplier_offer_disappeared",
    "price_swing",
]


@router.get("/alerts", response_model=AlertList)
def list_alerts(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[AlertService, Depends(get_alert_service)],
    kind: Annotated[AlertKindParam | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AlertList:
    return service.list_alerts(member=member, kind=kind, cursor=cursor, limit=limit)


@router.post("/alerts/{id}/dismiss", response_model=AlertDismissal)
def dismiss_alert(
    id: str,
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[AlertService, Depends(get_alert_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> AlertDismissal:
    return service.dismiss_alert(member=member, alert_id=id)
