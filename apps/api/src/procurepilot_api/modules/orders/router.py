from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.orders.schemas import (
    DeliveryReceiptCreate,
    OrderEvidenceProjection,
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderList,
    SupplierConfirmationCreate,
)
from procurepilot_api.modules.orders.service import OrdersService, get_orders_service
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(tags=["orders"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


def _order_limit() -> str:
    return get_settings().rate_limit_order_mutation


@router.post("/orders", status_code=status.HTTP_201_CREATED, response_model=PurchaseOrder)
@mutation_limiter.limit(_order_limit)
def create_order(
    request: Request,
    payload: Annotated[PurchaseOrderCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    response: Response,
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> PurchaseOrder:
    result, created = service.create_order(
        bearer_token=token, member=member, payload=payload, idempotency_key=idempotency_key
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/orders", response_model=PurchaseOrderList)
def list_orders(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PurchaseOrderList:
    return service.list_orders(bearer_token=token, cursor=cursor, limit=limit)


@router.get("/orders/{order_id}", response_model=OrderEvidenceProjection)
def get_order(
    order_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderEvidenceProjection:
    return service.get_order(bearer_token=token, order_id=order_id)


@router.post("/orders/{order_id}/submit", response_model=PurchaseOrder)
@mutation_limiter.limit(_order_limit)
def submit_order(
    request: Request,
    order_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> PurchaseOrder:
    return service.submit_order(
        bearer_token=token, member=member, order_id=order_id, idempotency_key=idempotency_key
    )


@router.post("/orders/{order_id}/confirmations", response_model=OrderEvidenceProjection)
@mutation_limiter.limit(_order_limit)
def record_confirmation(
    request: Request,
    order_id: UUID,
    payload: Annotated[SupplierConfirmationCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> OrderEvidenceProjection:
    return service.record_confirmation(
        bearer_token=token,
        member=member,
        order_id=order_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.post("/orders/{order_id}/receipts", response_model=OrderEvidenceProjection)
@mutation_limiter.limit(_order_limit)
def record_receipt(
    request: Request,
    order_id: UUID,
    payload: Annotated[DeliveryReceiptCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> OrderEvidenceProjection:
    return service.record_receipt(
        bearer_token=token,
        member=member,
        order_id=order_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
