from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.webhooks.schemas import (
    WebhookDelivery,
    WebhookDeliveryList,
    WebhookSubscription,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionList,
)
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.token_crypto import encrypt_token

SUBSCRIPTION_COLUMNS = "id,endpoint_url,events,status,created_at,updated_at"
DELIVERY_COLUMNS = (
    "id,subscription_id,audit_event_id,event_type,status,attempts,next_attempt_at,"
    "delivered_at,last_error,created_at"
)


def build_webhook_body(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_webhook_payload(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def retry_delay_seconds(attempt: int) -> int:
    return min(60 * (2 ** max(attempt - 1, 0)), 3600)


class WebhookService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def list_subscriptions(self, *, bearer_token: str) -> WebhookSubscriptionList:
        try:
            rows = (
                authenticated_client(self._settings, bearer_token)
                .table("webhook_subscription")
                .select(SUBSCRIPTION_COLUMNS)
                .order("created_at", desc=True)
                .execute()
            ).data
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return WebhookSubscriptionList(
            items=[WebhookSubscription.model_validate(row) for row in rows]
        )

    def create_subscription(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        payload: WebhookSubscriptionCreate,
    ) -> WebhookSubscriptionCreated:
        secret = secrets.token_urlsafe(32)
        row = {
            "tenant_id": str(member.tenant_id),
            "endpoint_url": str(payload.endpoint_url),
            "events": payload.events,
            "secret_encrypted": encrypt_token(
                secret, self._settings.webhook_token_encryption_key
            ),
            "created_by": str(member.membership_id),
        }
        try:
            result = (
                authenticated_client(self._settings, bearer_token)
                .table("webhook_subscription")
                .insert(row)
                .select(SUBSCRIPTION_COLUMNS)
                .single()
                .execute()
            ).data
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        self._audit(bearer_token, member, "webhooks.subscription_created", result["id"])
        return WebhookSubscriptionCreated.model_validate({**result, "secret": secret})

    def list_deliveries(self, *, bearer_token: str) -> WebhookDeliveryList:
        try:
            rows = (
                authenticated_client(self._settings, bearer_token)
                .table("webhook_delivery")
                .select(DELIVERY_COLUMNS)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            ).data
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return WebhookDeliveryList(items=[WebhookDelivery.model_validate(row) for row in rows])

    def pause_subscription(
        self, *, bearer_token: str, subscription_id: UUID
    ) -> WebhookSubscription:
        try:
            result = (
                authenticated_client(self._settings, bearer_token)
                .table("webhook_subscription")
                .update({"status": "paused"})
                .eq("id", str(subscription_id))
                .select(SUBSCRIPTION_COLUMNS)
                .single()
                .execute()
            ).data
        except APIError as exc:
            if getattr(exc, "code", None) == "PGRST116":
                raise NotFoundError(details={"resource": "webhook_subscription"}) from exc
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        return WebhookSubscription.model_validate(result)

    def _audit(
        self, bearer_token: str, member: CurrentMember, action: str, identifier: object
    ) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                target={"webhook_subscription_id": str(identifier)},
                outcome="success",
            ),
            bearer_token=bearer_token,
        )


def get_webhook_service() -> WebhookService:
    return WebhookService()
