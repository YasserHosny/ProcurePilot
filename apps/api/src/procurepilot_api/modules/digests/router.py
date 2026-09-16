from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.digests.schemas import (
    DigestSubscription,
    DigestSubscriptionCreate,
    DigestSubscriptionList,
    DigestSubscriptionUpdate,
    DigestView,
)
from procurepilot_api.modules.digests.service import DigestsService
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(tags=["digests"])


def _digest_mutation_limit() -> str:
    return get_settings().rate_limit_digest_mutation


def get_digests_service() -> DigestsService:
    return DigestsService()


@router.get("/digests/subscriptions", response_model=DigestSubscriptionList)
def list_subscriptions(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DigestsService, Depends(get_digests_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DigestSubscriptionList:
    return service.list_subscriptions(member=member, cursor=cursor, limit=limit)


@router.post(
    "/digests/subscriptions",
    status_code=status.HTTP_201_CREATED,
    response_model=DigestSubscription,
)
@mutation_limiter.limit(_digest_mutation_limit)
def create_subscription(
    request: Request,
    payload: Annotated[DigestSubscriptionCreate, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DigestsService, Depends(get_digests_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> DigestSubscription:
    return service.create_subscription(member=member, payload=payload, bearer_token=token)


@router.patch("/digests/subscriptions/{subscription_id}", response_model=DigestSubscription)
@mutation_limiter.limit(_digest_mutation_limit)
def update_subscription(
    request: Request,
    subscription_id: UUID,
    payload: Annotated[DigestSubscriptionUpdate, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DigestsService, Depends(get_digests_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> DigestSubscription:
    return service.update_subscription(
        member=member,
        subscription_id=subscription_id,
        payload=payload,
        bearer_token=token,
    )


@router.delete(
    "/digests/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@mutation_limiter.limit(_digest_mutation_limit)
def delete_subscription(
    request: Request,
    subscription_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DigestsService, Depends(get_digests_service)],
    token: Annotated[str, Depends(bearer_token)],
) -> Response:
    service.delete_subscription(
        member=member,
        subscription_id=subscription_id,
        bearer_token=token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/digests/latest", response_model=DigestView)
def get_latest_digest(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DigestsService, Depends(get_digests_service)],
) -> DigestView:
    return service.get_latest_digest(member=member)
