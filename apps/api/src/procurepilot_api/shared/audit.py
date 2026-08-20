from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.shared.logging import get_trace_id, redact

logger = logging.getLogger(__name__)

type AuditOutcome = Literal["success", "refused"]


class AuditEventCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: UUID | None = None
    actor_membership_id: UUID | None = None
    actor_email: str | None = None
    action: str
    target: dict[str, object] | None = None
    outcome: AuditOutcome
    trace_id: str | None = None


class AuditWriter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        """Append one audit event.

        Writes through the `record_audit_event` SECURITY DEFINER function (migration 0007), not
        the service role. The function is append-only by construction and validates the tenant
        against the caller's own claim, so pre-authentication and refused events can be recorded
        without putting an RLS bypass in the request path (research R4).

        `bearer_token` is the CALLER's access token and must be supplied for any event belonging
        to a workspace. Without it the request carries no JWT claims, `current_tenant_id()` is
        NULL, and the event is silently filed with no tenant — losing exactly the attribution the
        audit trail exists for. Omit it only for genuinely pre-authentication events such as a
        failed sign-in, which have no tenant by definition.
        """
        payload = {
            "tenant_id": str(event.tenant_id) if event.tenant_id else None,
            "actor_membership_id": (
                str(event.actor_membership_id) if event.actor_membership_id else None
            ),
            "actor_email": event.actor_email,
            "action": event.action,
            "target": redact(event.target) if event.target is not None else None,
            "outcome": event.outcome,
            "trace_id": event.trace_id or get_trace_id(),
        }
        try:
            self._client(bearer_token).rpc(
                "record_audit_event",
                {
                    "p_action": payload["action"],
                    "p_outcome": payload["outcome"],
                    "p_tenant_id": payload["tenant_id"],
                    "p_actor_membership_id": payload["actor_membership_id"],
                    "p_actor_email": payload["actor_email"],
                    "p_target": payload["target"],
                    "p_trace_id": payload["trace_id"],
                },
            ).execute()
        except Exception as exc:
            logger.exception(
                "Failed to append audit event",
                extra={"audit_action": event.action, "audit_outcome": event.outcome},
            )
            raise ServiceUnavailableError(details={"dependency": "audit_event"}) from exc

    def _client(self, bearer_token: str | None) -> Client:
        # The anon key opens the connection; the caller's token, when present, supplies the claims
        # that record_audit_event validates against. The service-role key deliberately never
        # appears here.
        client = create_client(
            self._settings.supabase_url,
            self._settings.supabase_anon_key.get_secret_value(),
        )
        if bearer_token:
            client.postgrest.auth(bearer_token)
        return client


def get_audit_writer() -> AuditWriter:
    return AuditWriter()
