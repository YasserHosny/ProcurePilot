from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.webhooks.schemas import (
    WebhookDeliveryList,
    WebhookSubscription,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionList,
)
from procurepilot_api.modules.webhooks.service import WebhookService, get_webhook_service

router = APIRouter(tags=["webhooks"])


@router.get("/webhooks/deliveries", response_model=WebhookDeliveryList)
def list_deliveries(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> WebhookDeliveryList:
    return service.list_deliveries(bearer_token=token)


@router.get("/webhooks/subscriptions", response_model=WebhookSubscriptionList)
def list_subscriptions(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> WebhookSubscriptionList:
    return service.list_subscriptions(bearer_token=token)


@router.post(
    "/webhooks/subscriptions",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookSubscriptionCreated,
)
def create_subscription(
    payload: WebhookSubscriptionCreate,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> WebhookSubscriptionCreated:
    return service.create_subscription(bearer_token=token, member=member, payload=payload)


@router.post("/webhooks/subscriptions/{subscription_id}/pause", response_model=WebhookSubscription)
def pause_subscription(
    subscription_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(require_role(MemberRole.owner))],
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> WebhookSubscription:
    return service.pause_subscription(bearer_token=token, subscription_id=subscription_id)
