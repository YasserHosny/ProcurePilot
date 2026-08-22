from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.modules.billing.schemas import BillingAccount, LimitCheck
from procurepilot_api.modules.billing.service import BillingService, get_billing_service

router = APIRouter(tags=["billing"])


@router.get("/billing/account", response_model=BillingAccount)
def current_account(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> BillingAccount:
    return service.current_account(member=member)


@router.get("/billing/limits/active-catalogue-products", response_model=LimitCheck)
def active_catalogue_product_limit(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[BillingService, Depends(get_billing_service)],
) -> LimitCheck:
    return service.check_limit(member=member, resource="active_catalogue_products")
