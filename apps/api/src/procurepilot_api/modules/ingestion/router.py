import base64
import logging
from typing import Annotated
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Body, Depends, Header, Request, Response, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from supabase import create_client

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.ingestion.schemas import TenantEmailConfig, TenantEmailConfigUpdate
from procurepilot_api.modules.ingestion.service import (
    IngestionConfigService,
    get_ingestion_config_service,
)
from procurepilot_api.modules.ingestion.webhook_security import (
    verify_mailgun_signature,
    verify_shared_secret,
)
from procurepilot_api.shared.rate_limit import limiter, mutation_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])
OWNER = (MemberRole.owner,)


def _email_config_mutation_limit() -> str:
    return get_settings().rate_limit_ingestion_config_mutation


def _webhook_limit() -> str:
    return get_settings().rate_limit_inbound_email_webhook


@router.get("/tenants/email-config", response_model=TenantEmailConfig)
def get_email_config(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[IngestionConfigService, Depends(get_ingestion_config_service)],
) -> TenantEmailConfig:
    config = service.get_config(member=member)
    if config is None:
        raise NotFoundError(details={"resource": "tenant_email_config"})
    return config


@router.put("/tenants/email-config", response_model=TenantEmailConfig)
@mutation_limiter.limit(_email_config_mutation_limit)
def update_email_config(
    request: Request,
    payload: Annotated[TenantEmailConfigUpdate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    service: Annotated[IngestionConfigService, Depends(get_ingestion_config_service)],
    token: Annotated[str, Depends(bearer_token)],
) -> TenantEmailConfig:
    return service.update_config(member=member, payload=payload, bearer_token=token)


@router.post("/tenants/email-config/enable", response_model=TenantEmailConfig)
@mutation_limiter.limit(_email_config_mutation_limit)
def enable_email_config(
    request: Request,
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    service: Annotated[IngestionConfigService, Depends(get_ingestion_config_service)],
    token: Annotated[str, Depends(bearer_token)],
) -> TenantEmailConfig:
    return service.set_enabled(member=member, enabled=True, bearer_token=token)


@router.post("/tenants/email-config/disable", response_model=TenantEmailConfig)
@mutation_limiter.limit(_email_config_mutation_limit)
def disable_email_config(
    request: Request,
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    service: Annotated[IngestionConfigService, Depends(get_ingestion_config_service)],
    token: Annotated[str, Depends(bearer_token)],
) -> TenantEmailConfig:
    return service.set_enabled(member=member, enabled=False, bearer_token=token)


@router.post("/webhooks/inbound-email", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(_webhook_limit)
async def inbound_email_webhook(
    request: Request,
    x_ingestion_webhook_secret: Annotated[str | None, Header()] = None,
) -> Response:
    """T014. Public — no bearer auth, called by the configured mail provider, not a
    ProcurePilot user. Signature verification is the entire security boundary here; see
    webhook_security.py for exactly what each provider mode actually verifies today."""
    settings = get_settings()
    provider = settings.ingestion_email_provider

    if provider == "mailgun":
        form = await request.form()
        timestamp = str(form.get("timestamp") or "")
        token = str(form.get("token") or "")
        signature = str(form.get("signature") or "")
        verify_mailgun_signature(settings, timestamp=timestamp, token=token, signature=signature)
        recipient = str(form.get("recipient") or "")
        raw_mime = form.get("body-mime")
        raw_email_bytes = (
            raw_mime.encode("utf-8") if isinstance(raw_mime, str) else b""
        )
    else:
        verify_shared_secret(settings, provided_secret=x_ingestion_webhook_secret)
        body = await request.json()
        recipient = str(body.get("recipient") or "")
        raw_b64 = str(body.get("raw_email_base64") or "")
        try:
            raw_email_bytes = base64.b64decode(raw_b64) if raw_b64 else b""
        except Exception as exc:
            raise UnprocessableEntityError(details={"reason": "invalid_base64"}) from exc

    if not recipient or not raw_email_bytes:
        raise UnprocessableEntityError(details={"reason": "missing_recipient_or_body"})

    if len(raw_email_bytes) > settings.ingestion_max_email_bytes:
        # Accepted-then-discarded, not a 4xx: from the provider's perspective the webhook call
        # itself succeeded (it must not retry), the email itself is what is refused. Recorded
        # exactly like any other rejection once the tenant is known, below.
        logger.warning("Inbound email exceeded max size for recipient %s", recipient)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        tenant_config = _lookup_tenant_by_address(conn, recipient)
        if tenant_config is None:
            # Unknown address: a standard bounce, no existence leak (research R10) — same 202,
            # so probing for valid tenant addresses learns nothing from the response shape.
            logger.info("Inbound email to unknown forwarding address")
            return Response(status_code=status.HTTP_202_ACCEPTED)

        tenant_id = tenant_config["tenant_id"]
        if not tenant_config["enabled"]:
            return Response(status_code=status.HTTP_202_ACCEPTED)

        allowlist = tenant_config.get("domain_allowlist")
        sender_domain = _sender_domain_hint(raw_email_bytes)
        if allowlist and sender_domain not in allowlist:
            return Response(status_code=status.HTTP_202_ACCEPTED)

        if not _check_and_increment_daily_count(conn, tenant_config):
            return Response(status_code=status.HTTP_202_ACCEPTED)

        raw_email_path = f"{tenant_id}/raw-email/{uuid4()}.eml"
        client = create_client(
            settings.supabase_url, settings.supabase_service_role_key.get_secret_value()
        )
        client.storage.from_(settings.ingestion_raw_bucket).upload(
            raw_email_path, raw_email_bytes, {"content-type": "message/rfc822", "upsert": "true"}
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                insert into ingestion_jobs (tenant_id, job_type, status, payload)
                values (%s, 'email_ingest', 'pending', %s)
                """,
                (tenant_id, Jsonb({"raw_email_path": raw_email_path})),
            )
        conn.commit()

    return Response(status_code=status.HTTP_202_ACCEPTED)


def _lookup_tenant_by_address(conn: object, forwarding_address: str) -> dict[str, object] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select * from tenant_email_config where lower(forwarding_address) = lower(%s)",
            (forwarding_address,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _sender_domain_hint(raw_email_bytes: bytes) -> str | None:
    # Cheap best-effort peek at the From header without a full parse, purely for the domain
    # allowlist check — the worker does the real, validated parse in T011/T009.
    try:
        head = raw_email_bytes[:8192].decode("utf-8", errors="ignore")
        for line in head.splitlines():
            if line.lower().startswith("from:") and "@" in line:
                return line.rsplit("@", 1)[-1].strip().strip(">").lower()
    except Exception:
        return None
    return None


def _check_and_increment_daily_count(conn: object, tenant_config: dict[str, object]) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            update tenant_email_config
            set daily_count = case
                  when daily_count_date = current_date then daily_count + 1 else 1
                end,
                daily_count_date = current_date
            where tenant_id = %(tenant_id)s
              and (daily_count_date <> current_date or daily_count < daily_limit)
            returning daily_count
            """,
            {"tenant_id": tenant_config["tenant_id"]},
        )
        row = cur.fetchone()
    return row is not None
