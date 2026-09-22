from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.offers.basket_service import BasketService, get_basket_service
from procurepilot_api.modules.offers.negotiation_briefs import (
    NegotiationBriefService,
    get_negotiation_brief_service,
)
from procurepilot_api.modules.offers.refresh_schedule_service import (
    create_schedule,
    list_schedules,
    update_schedule,
)
from procurepilot_api.modules.offers.schemas import (
    AdvancedBasketOptimiseRequest,
    BasketOptimiseRequest,
    BasketSplitJob,
    NegotiationBrief,
    NegotiationBriefDismissRequest,
    NegotiationBriefList,
    OfferComparison,
    OfferList,
    PriceHistoryResponse,
    RefreshSchedule,
    RefreshScheduleCreate,
    RefreshScheduleList,
    RefreshScheduleUpdate,
    SupplierCommercialTerm,
    SupplierCommercialTermCreate,
    SupplierCommercialTermList,
    SupplierRiskList,
    SupplierRiskRecomputeResponse,
    SupplierRiskSnapshot,
    SupplierScorecard,
)
from procurepilot_api.modules.offers.service import OfferService, get_offer_service
from procurepilot_api.modules.offers.supplier_iq import (
    SupplierIqService,
    get_supplier_iq_service,
)
from procurepilot_api.modules.offers.supplier_terms import (
    SupplierTermsService,
    get_supplier_terms_service,
)
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(tags=["smart-compare"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


def _schedule_mutation_limit() -> str:
    return get_settings().rate_limit_schedule_mutation


@router.get("/refresh-schedules", response_model=RefreshScheduleList)
def list_refresh_schedules(
    member: Annotated[CurrentMember, Depends(current_member)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RefreshScheduleList:
    return list_schedules(member=member, cursor=cursor, limit=limit)


@router.post(
    "/refresh-schedules",
    status_code=status.HTTP_201_CREATED,
    response_model=RefreshSchedule,
)
@mutation_limiter.limit(_schedule_mutation_limit)
def create_refresh_schedule(
    request: Request,
    payload: Annotated[RefreshScheduleCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> RefreshSchedule:
    return create_schedule(member=member, payload=payload, bearer_token=token)


@router.patch("/refresh-schedules/{schedule_id}", response_model=RefreshSchedule)
@mutation_limiter.limit(_schedule_mutation_limit)
def update_refresh_schedule(
    request: Request,
    schedule_id: UUID,
    payload: Annotated[RefreshScheduleUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> RefreshSchedule:
    return update_schedule(
        member=member, schedule_id=schedule_id, payload=payload, bearer_token=token
    )


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
    payload: Annotated[BasketOptimiseRequest | AdvancedBasketOptimiseRequest, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[BasketService, Depends(get_basket_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> BasketSplitJob:
    return service.create_job(member=member, payload=payload, bearer_token=token)


@router.get("/baskets/{id}", response_model=BasketSplitJob)
def get_basket(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[BasketService, Depends(get_basket_service)],
) -> BasketSplitJob:
    return service.get_job(member=member, job_id=id)


@router.get("/suppliers/{supplier_id}/scorecard", response_model=SupplierScorecard)
def get_supplier_scorecard(
    supplier_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[SupplierIqService, Depends(get_supplier_iq_service)],
    window_months: Annotated[int, Query(ge=1, le=24)] = 6,
) -> SupplierScorecard:
    return service.get_scorecard(
        member=member,
        supplier_id=supplier_id,
        bearer_token=token,
        window_months=window_months,
    )


@router.post(
    "/supplier-iq/recompute",
    response_model=SupplierRiskRecomputeResponse,
    operation_id="recomputeSupplierRisk",
)
@mutation_limiter.limit(_schedule_mutation_limit)
def recompute_supplier_risk(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[SupplierIqService, Depends(get_supplier_iq_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> SupplierRiskRecomputeResponse:
    result = service.recompute_all(
        member=member,
        idempotency_key=idempotency_key,
        bearer_token=token,
    )
    return SupplierRiskRecomputeResponse(
        generated_snapshots=result.generated_snapshots,
        release_posture=result.release_posture,
    )


@router.get(
    "/supplier-iq/risks",
    response_model=SupplierRiskList,
    operation_id="listSupplierRisks",
)
def list_supplier_risks(
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[SupplierIqService, Depends(get_supplier_iq_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SupplierRiskList:
    page = service.list_risks(member=_member, cursor=cursor, limit=limit)
    return SupplierRiskList(
        items=tuple(SupplierRiskSnapshot.model_validate(item) for item in page.items),
        next_cursor=page.next_cursor,
    )


@router.post(
    "/suppliers/{supplier_id}/negotiation-briefs",
    status_code=status.HTTP_201_CREATED,
    response_model=NegotiationBrief,
    operation_id="prepareNegotiationBrief",
)
@mutation_limiter.limit(_schedule_mutation_limit)
def prepare_negotiation_brief(
    request: Request,
    supplier_id: UUID,
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[NegotiationBriefService, Depends(get_negotiation_brief_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> NegotiationBrief:
    return service.prepare_for_supplier(
        member=member,
        supplier_id=supplier_id,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/negotiation-briefs",
    response_model=NegotiationBriefList,
    operation_id="listNegotiationBriefs",
)
def list_negotiation_briefs(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[NegotiationBriefService, Depends(get_negotiation_brief_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NegotiationBriefList:
    return service.list(member=member, cursor=cursor, limit=limit)


@router.get(
    "/negotiation-briefs/{brief_id}",
    response_model=NegotiationBrief,
    operation_id="getNegotiationBrief",
)
def get_negotiation_brief(
    brief_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[NegotiationBriefService, Depends(get_negotiation_brief_service)],
) -> NegotiationBrief:
    return service.get(member=member, brief_id=brief_id)


@router.post(
    "/negotiation-briefs/{brief_id}/acknowledge",
    response_model=NegotiationBrief,
    operation_id="acknowledgeNegotiationBrief",
)
@mutation_limiter.limit(_schedule_mutation_limit)
def acknowledge_negotiation_brief(
    request: Request,
    brief_id: UUID,
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[NegotiationBriefService, Depends(get_negotiation_brief_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> NegotiationBrief:
    return service.acknowledge(
        member=member,
        brief_id=brief_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/negotiation-briefs/{brief_id}/dismiss",
    response_model=NegotiationBrief,
    operation_id="dismissNegotiationBrief",
)
@mutation_limiter.limit(_schedule_mutation_limit)
def dismiss_negotiation_brief(
    request: Request,
    brief_id: UUID,
    payload: Annotated[NegotiationBriefDismissRequest, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[NegotiationBriefService, Depends(get_negotiation_brief_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> NegotiationBrief:
    return service.dismiss(
        member=member,
        brief_id=brief_id,
        idempotency_key=idempotency_key,
        reason=payload.reason,
    )


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
