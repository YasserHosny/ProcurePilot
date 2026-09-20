from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.partner.schemas import (
    OrderEvidenceProjection,
    ProductList,
    ProductListStatus,
    PurchaseOrderList,
)
from procurepilot_api.modules.partner.service import PartnerService, get_partner_service

router = APIRouter(prefix="/partner", tags=["partner"])


@router.get("/orders", response_model=PurchaseOrderList)
def list_partner_orders(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[PartnerService, Depends(get_partner_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PurchaseOrderList:
    return service.list_orders(bearer_token=token, cursor=cursor, limit=limit)


@router.get("/orders/{order_id}", response_model=OrderEvidenceProjection)
def get_partner_order(
    order_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[PartnerService, Depends(get_partner_service)],
) -> OrderEvidenceProjection:
    return service.get_order(bearer_token=token, order_id=order_id)


@router.get("/catalogue/products", response_model=ProductList)
def list_partner_products(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[PartnerService, Depends(get_partner_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Annotated[ProductListStatus, Query()] = "active",
    q: Annotated[str | None, Query()] = None,
) -> ProductList:
    return service.list_products(
        bearer_token=token,
        cursor=cursor,
        limit=limit,
        status=status,
        q=q,
    )
