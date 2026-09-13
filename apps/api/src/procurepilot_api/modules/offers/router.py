from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, status

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.offers.basket_service import BasketService, get_basket_service
from procurepilot_api.modules.offers.schemas import (
    BasketOptimiseRequest,
    BasketSplitJob,
    OfferComparison,
    OfferList,
    PriceHistoryResponse,
    SupplierCommercialTerm,
    SupplierCommercialTermCreate,
    SupplierCommercialTermList,
)
from procurepilot_api.modules.offers.service import OfferService, get_offer_service
from procurepilot_api.modules.offers.supplier_terms import (
    SupplierTermsService,
    get_supplier_terms_service,
)

router = APIRouter(tags=["smart-compare"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.get("/offers", response_model=OfferList)
def list_offers(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OfferService, Depends(get_offer_service)],
    product_id: Annotated[UUID, Query()],
    quantity: Annotated[Decimal, Query(gt=0)],
    include_expired: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OfferList:
    return service.list_offers(
        member=member,
        product_id=product_id,
        quantity=quantity,
        include_expired=include_expired,
        cursor=cursor,
        limit=limit,
    )


@router.get("/offers/compare", response_model=OfferComparison)
def compare_offers(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OfferService, Depends(get_offer_service)],
    product_id: Annotated[UUID, Query()],
    quantity: Annotated[Decimal, Query(gt=0)],
) -> OfferComparison:
    return service.compare_offers(member=member, product_id=product_id, quantity=quantity)


@router.get("/products/{product_id}/price-history", response_model=PriceHistoryResponse)
def price_history(
    product_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[OfferService, Depends(get_offer_service)],
    supplier_id: Annotated[UUID | None, Query()] = None,
    window_months: Annotated[int, Query(ge=1, le=24)] = 6,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> PriceHistoryResponse:
    return service.price_history(
        member=member,
        product_id=product_id,
        supplier_id=supplier_id,
        window_months=window_months,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/baskets/optimise",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BasketSplitJob,
)
def optimise_basket(
    payload: Annotated[BasketOptimiseRequest, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[BasketService, Depends(get_basket_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> BasketSplitJob:
    return service.create_job(member=member, payload=payload)


@router.get("/baskets/{id}", response_model=BasketSplitJob)
def get_basket(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[BasketService, Depends(get_basket_service)],
) -> BasketSplitJob:
    return service.get_job(member=member, job_id=id)


@router.get(
    "/suppliers/{supplier_id}/commercial-terms",
    response_model=SupplierCommercialTermList,
)
def list_supplier_commercial_terms(
    supplier_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[SupplierTermsService, Depends(get_supplier_terms_service)],
) -> SupplierCommercialTermList:
    return service.list_terms(member=member, supplier_id=supplier_id)


@router.post(
    "/suppliers/{supplier_id}/commercial-terms",
    status_code=status.HTTP_201_CREATED,
    response_model=SupplierCommercialTerm,
)
def create_supplier_commercial_term(
    supplier_id: UUID,
    payload: Annotated[SupplierCommercialTermCreate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[SupplierTermsService, Depends(get_supplier_terms_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> SupplierCommercialTerm:
    return service.create_term(member=member, supplier_id=supplier_id, payload=payload)
