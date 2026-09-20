from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.webhooks.service import (
    build_webhook_body,
    retry_delay_seconds,
    sign_webhook_payload,
)
from procurepilot_api.shared.token_crypto import decrypt_token

logger = logging.getLogger(__name__)


def tick(settings: Settings, *, http_client: httpx.Client | None = None) -> dict[str, int]:
    stats = {"claimed": 0, "succeeded": 0, "retrying": 0, "failed": 0}
    with psycopg.connect(
        settings.database_url.get_secret_value(), prepare_threshold=None
    ) as conn:
        claimed = _claim_deliveries(conn, settings.webhook_max_attempts)
        stats["claimed"] = len(claimed)
        conn.commit()

    client = http_client or httpx.Client(timeout=settings.webhook_request_timeout_seconds)
    close_client = http_client is None
    try:
        for delivery in claimed:
            outcome = _deliver_one(settings, client, delivery)
            stats[outcome] += 1
    finally:
        if close_client:
            client.close()
    return stats


def _claim_deliveries(
    conn: psycopg.Connection[Any], max_attempts: int, limit: int = 50
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select d.*, s.endpoint_url, s.secret_encrypted, s.status as subscription_status
              from webhook_delivery d
              join webhook_subscription s on s.tenant_id = d.tenant_id and s.id = d.subscription_id
             where s.status = 'active'
               and d.attempts < %(max_attempts)s
               and (
                 (d.status = 'pending' and d.next_attempt_at <= now())
                 or (d.status = 'processing' and d.locked_at < now() - interval '10 minutes')
               )
             order by d.next_attempt_at, d.created_at
             limit %(limit)s
             for update of d skip locked
            """,
            {"max_attempts": max_attempts, "limit": limit},
        )
        rows = [dict(row) for row in cur.fetchall()]
        claimed: list[dict[str, Any]] = []
        for row in rows:
            cur.execute(
                """
                update webhook_delivery
                   set status = 'processing', attempts = attempts + 1,
                       locked_at = now(), locked_by = 'webhook_worker', updated_at = now()
                 where id = %(id)s
                returning *
                """,
                {"id": row["id"]},
            )
            updated = cur.fetchone()
            if updated is not None:
                claimed.append({**row, **dict(updated)})
        return claimed


def _deliver_one(settings: Settings, client: httpx.Client, delivery: dict[str, Any]) -> str:
    delivery_id = UUID(str(delivery["id"]))
    body = build_webhook_body(delivery["payload"])
    secret = decrypt_token(
        str(delivery["secret_encrypted"]), settings.webhook_token_encryption_key
    )
    headers = {
        "Content-Type": "application/json",
        "X-ProcurePilot-Event-Id": str(delivery["event_id"]),
        "X-ProcurePilot-Event-Type": str(delivery["event_type"]),
        "X-ProcurePilot-Signature": sign_webhook_payload(body, secret),
    }
    try:
        response = client.post(str(delivery["endpoint_url"]), content=body, headers=headers)
        response.raise_for_status()
    except Exception as exc:
        attempts = int(delivery["attempts"])
        if attempts >= settings.webhook_max_attempts:
            _mark_failed(settings, delivery_id, str(exc))
            return "failed"
        _mark_retry(settings, delivery_id, attempts, str(exc))
        return "retrying"
    _mark_succeeded(settings, delivery_id)
    return "succeeded"


def _mark_succeeded(settings: Settings, delivery_id: UUID) -> None:
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        conn.execute(
            """
            update webhook_delivery
               set status = 'succeeded', delivered_at = now(), locked_at = null,
                   locked_by = null, last_error = null, updated_at = now()
             where id = %s
            """,
            (delivery_id,),
        )
        conn.commit()


def _mark_retry(settings: Settings, delivery_id: UUID, attempts: int, error: str) -> None:
    next_attempt = datetime.now(UTC) + timedelta(seconds=retry_delay_seconds(attempts))
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        conn.execute(
            """
            update webhook_delivery
               set status = 'pending', next_attempt_at = %s, locked_at = null,
                   locked_by = null, last_error = %s, updated_at = now()
             where id = %s
            """,
            (next_attempt, error[:2000], delivery_id),
        )
        conn.commit()


def _mark_failed(settings: Settings, delivery_id: UUID, error: str) -> None:
    with psycopg.connect(settings.database_url.get_secret_value(), prepare_threshold=None) as conn:
        conn.execute(
            """
            update webhook_delivery
               set status = 'failed', locked_at = null, locked_by = null,
                   last_error = %s, updated_at = now()
             where id = %s
            """,
            (error[:2000], delivery_id),
        )
        conn.commit()


def run_loop(settings: Settings, *, once: bool = False, interval_seconds: int = 10) -> None:
    logger.info("Starting webhook worker (once=%s, interval=%ss)", once, interval_seconds)
    while True:
        try:
            stats = tick(settings)
            if stats["claimed"]:
                logger.info("Webhook delivery pass completed: %s", stats)
        except Exception:
            logger.exception("Error during webhook delivery worker pass")
        if once:
            break
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=10)
    args = parser.parse_args()
    run_loop(get_settings(), once=args.once, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    main()
