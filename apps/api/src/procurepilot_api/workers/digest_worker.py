from __future__ import annotations

import argparse
import json
import logging
import smtplib
import time
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import urljoin
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.digests.renderer import render_digest
from procurepilot_api.modules.digests.service import DigestsService
from procurepilot_api.modules.reports.schedules import derive_weekly_window, next_run_after
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

logger = logging.getLogger(__name__)


def tick(settings: Settings) -> dict[str, int]:
    """Execute one pass: claim due active subscriptions, render and deliver, and
    advance run times.
    """
    stats = {
        "claimed": 0,
        "succeeded": 0,
        "failed": 0,
        "email_unconfigured": 0,
        "skipped": 0,
    }
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        claimed = _claim_due_subscriptions(conn)
        stats["claimed"] = len(claimed)

        for sub in claimed:
            outcome = _process_subscription(conn, settings, sub)
            if outcome in stats:
                stats[outcome] += 1
        conn.commit()

    return stats


def process_digest_subscription(
    subscription_id: UUID,
    tenant_id: UUID,
    settings: Settings | None = None,
) -> str:
    """Entrypoint for queue workers: re-derives tenant and delivers subscription."""
    active_settings = settings or get_settings()
    with psycopg.connect(active_settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, tenant_id, membership_id, locale, channel, filters, next_run_at
                from digest_subscription
                where id = %s
                for update
                """,
                (subscription_id,),
            )
            sub = cur.fetchone()

        if sub is None:
            logger.warning("Subscription %s not found in database; ignoring hint", subscription_id)
            return "not_found"

        if UUID(str(sub["tenant_id"])) != tenant_id:
            logger.error(
                "Tenant mismatch: hint was %s, row belongs to %s. Rejecting untrusted hint.",
                tenant_id,
                sub["tenant_id"],
            )
            return "tenant_mismatch"

        outcome = _process_subscription(conn, active_settings, dict(sub))
        conn.commit()
        return outcome


def _claim_due_subscriptions(conn: psycopg.Connection) -> list[dict[str, object]]:
    """Claim active subscriptions that are due for delivery using FOR UPDATE SKIP LOCKED."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, membership_id, locale, channel, filters, next_run_at
            from digest_subscription
            where status = 'active'
              and next_run_at <= now()
            for update skip locked
            """
        )
        return [dict(r) for r in cur.fetchall()]


def _process_subscription(
    conn: psycopg.Connection,
    settings: Settings,
    sub: dict[str, object],
) -> str:
    sub_id = UUID(str(sub["id"]))
    tenant_id = UUID(str(sub["tenant_id"]))
    membership_id = UUID(str(sub["membership_id"]))
    channel = str(sub.get("channel") or "in_app")
    locale = str(sub.get("locale") or "en")

    # Re-derive membership and tenant settings to ensure membership is active
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select m.status as member_status, m.email as member_email,
                   t.reporting_timezone
            from membership m
            join tenant t on t.id = m.tenant_id
            where m.id = %s and m.tenant_id = %s
            """,
            (membership_id, tenant_id),
        )
        ctx = cur.fetchone()

    now = datetime.now(UTC)
    if ctx is None or ctx.get("member_status") != "active":
        logger.info("Skipping digest for inactive membership %s", membership_id)
        _advance_subscription(conn, sub_id, now, "UTC")
        return "skipped"

    tz_name = str(ctx.get("reporting_timezone") or "UTC")
    member_email = str(ctx.get("member_email") or "")
    period_start, period_end = derive_weekly_window(now, tz_name)

    filters = sub.get("filters")
    if isinstance(filters, str):
        filters = json.loads(filters)
    branch_id = None
    if isinstance(filters, dict) and filters.get("branch_id"):
        branch_id = UUID(str(filters["branch_id"]))

    digests_svc = DigestsService(settings)
    sections = digests_svc._assemble_sections(
        conn,
        tenant_id=tenant_id,
        membership_id=membership_id,
        period_start=period_start,
        period_end=period_end,
        branch_id=branch_id,
        now=now,
    )

    from procurepilot_api.modules.digests.schemas import DigestView

    view = DigestView(
        subscription_id=sub_id,
        period_start=period_start,
        period_end=period_end,
        sections=sections,
        rendered_at=now,
        delivery_status="succeeded",
    )

    if channel == "email":
        if not settings.email_configured:
            _record_delivery(conn, sub_id, now, "email_unconfigured")
            _record_delivery_audit(
                tenant_id=tenant_id,
                sub_id=sub_id,
                membership_id=membership_id,
                status="email_unconfigured",
                detail="SMTP server or sender address is not configured",
            )
            _advance_subscription(conn, sub_id, now, tz_name)
            return "email_unconfigured"

        # Deliver email via SMTP
        settings_url = urljoin(settings.web_api_base_url, "/reports/digest-settings")
        subject, html_content, text_content = render_digest(
            view,
            locale=locale,
            web_base_url=settings.web_api_base_url,
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = member_email
        msg["List-Unsubscribe"] = f"<{settings_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg.set_content(text_content)
        msg.add_alternative(html_content, subtype="html")

        try:
            _send_smtp(settings, msg)
            _record_delivery(conn, sub_id, now, "succeeded")
            _record_delivery_audit(
                tenant_id=tenant_id,
                sub_id=sub_id,
                membership_id=membership_id,
                status="succeeded",
                detail="Delivered via SMTP",
            )
            _advance_subscription(conn, sub_id, now, tz_name)
            return "succeeded"
        except Exception as exc:
            # Redact sensitive info from log and audit
            safe_err = f"{type(exc).__name__}: delivery_failed"
            logger.error("SMTP delivery failed for subscription %s: %s", sub_id, safe_err)
            _record_delivery(conn, sub_id, now, "failed")
            _record_delivery_audit(
                tenant_id=tenant_id,
                sub_id=sub_id,
                membership_id=membership_id,
                status="failed",
                detail=safe_err,
            )
            _advance_subscription(conn, sub_id, now, tz_name)
            return "failed"

    # channel == "in_app"
    _record_delivery(conn, sub_id, now, "succeeded")
    _record_delivery_audit(
        tenant_id=tenant_id,
        sub_id=sub_id,
        membership_id=membership_id,
        status="succeeded",
        detail="Rendered in-app digest",
    )
    _advance_subscription(conn, sub_id, now, tz_name)
    return "succeeded"


def _send_smtp(settings: Settings, msg: EmailMessage) -> None:
    if not settings.smtp_host:
        raise ValueError("smtp_host_not_configured")
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    try:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _advance_subscription(
    conn: psycopg.Connection, sub_id: UUID, now: datetime, tz_name: str
) -> None:
    next_run = next_run_after(0, now, tz_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            update digest_subscription
            set next_run_at = %s, updated_at = %s
            where id = %s
            """,
            (next_run, now, sub_id),
        )


def _record_delivery(
    conn: psycopg.Connection, sub_id: UUID, delivered_at: datetime, status: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update digest_subscription
            set last_delivery_at = %s, last_delivery_status = %s
            where id = %s
            """,
            (delivered_at, status, sub_id),
        )


def _record_delivery_audit(
    *,
    tenant_id: UUID,
    sub_id: UUID,
    membership_id: UUID,
    status: str,
    detail: str,
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=tenant_id,
            actor_membership_id=None,  # Worker is a system actor per FR-011
            actor_email="system@procurepilot.internal",
            action=f"digests.delivery_{status}",
            target={"subscription_id": str(sub_id), "membership_id": str(membership_id)},
            outcome="success" if status == "succeeded" else "failure",
            trace_id=get_trace_id(),
        ),
        bearer_token=None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ProcurePilot Digest Worker")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60)",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.api_log_level.upper(), logging.INFO))
    logger.info("Starting ProcurePilot Digest Worker (once=%s)", args.once)

    if args.once:
        stats = tick(settings)
        logger.info("Completed single pass: %s", stats)
        return

    while True:
        try:
            stats = tick(settings)
            if stats["claimed"] > 0:
                logger.info("Scheduler pass completed: %s", stats)
        except Exception:
            logger.exception("Error executing digest worker tick")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
