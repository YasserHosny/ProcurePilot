from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings

logger = logging.getLogger(__name__)

PUSH_QUEUE_NAME = "push-notifications"
RETRY_SWEEP_AGE = timedelta(minutes=5)
MAX_PUSH_ATTEMPTS = 5


def process_push_notification(notification_id: UUID | str) -> None:
    settings = get_settings()
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            notification = _notification_row(conn, UUID(str(notification_id)))
            if notification is None:
                logger.warning(
                    "push notification not found",
                    extra={"notification_id": str(notification_id)},
                )
                return
            registrations = _device_registrations(conn, notification)
            payload = _payload(notification)
            successes = 0
            for registration in registrations:
                try:
                    if _send_to_device(registration, payload):
                        successes += 1
                except Exception:
                    logger.exception(
                        "push device send failed",
                        extra={
                            "notification_id": str(notification["id"]),
                            "device_registration_id": str(registration["id"]),
                        },
                    )

            status = "sent" if successes > 0 or not registrations else "failed"
            _mark_attempted(conn, UUID(str(notification["id"])), status=status)
            conn.commit()
    except Exception:
        logger.exception(
            "push notification job failed",
            extra={"notification_id": str(notification_id)},
        )


def sweep_stale_push_notifications() -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - RETRY_SWEEP_AGE
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            rows = _stale_notifications(conn, cutoff=cutoff)
        enqueued = 0
        for row in rows:
            try:
                _enqueue_push_job(settings, UUID(str(row["id"])))
            except Exception:
                logger.exception(
                    "push notification retry enqueue failed",
                    extra={"notification_id": str(row["id"])},
                )
                continue
            enqueued += 1
        return enqueued
    except Exception:
        logger.exception("push notification retry sweep failed")
        return 0


def _notification_row(
    conn: psycopg.Connection, notification_id: UUID
) -> dict[str, object] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, purchase_request_id, member_id, status,
                   attempts, created_at, sent_at
            from push_notification
            where id = %s
            """,
            (notification_id,),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def _device_registrations(
    conn: psycopg.Connection, notification: dict[str, object]
) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id, tenant_id, member_id, platform, push_token, last_seen_at,
                   created_at
            from device_registration
            where tenant_id = %s and member_id = %s
            order by last_seen_at desc, id
            """,
            (notification["tenant_id"], notification["member_id"]),
        )
        return [dict(row) for row in cur.fetchall()]


def _payload(notification: dict[str, object]) -> dict[str, str]:
    return {
        "purchase_request_id": str(notification["purchase_request_id"]),
        "notification_id": str(notification["id"]),
    }


def _send_to_device(
    registration: dict[str, object], payload: dict[str, str]
) -> bool:
    """No FCM/APNs credentials exist anywhere in this codebase yet (Phase 6 work) — this only
    logs what a real send would carry. Returning `True` here would mark the notification `sent`
    for a push nothing actually delivered, which is exactly the failure mode this table's own
    outbox design exists to catch (research.md R1). Returning `False` means the notification
    lands in `failed` and stays visible to the retry sweep instead of being silently lost —
    honest about "not yet delivered," not a claim of success. Replace this with a real
    provider call in Phase 6; the outbox/sweep plumbing around it does not need to change.
    """
    logger.info(
        "stub push send — no real provider configured, not marking delivered",
        extra={
            "device_registration_id": str(registration["id"]),
            "platform": str(registration["platform"]),
            "payload": payload,
        },
    )
    return False


def _mark_attempted(
    conn: psycopg.Connection, notification_id: UUID, *, status: str
) -> None:
    sent_at = datetime.now(UTC) if status == "sent" else None
    with conn.cursor() as cur:
        cur.execute(
            """
            update push_notification
            set status = %s,
                attempts = attempts + 1,
                sent_at = %s
            where id = %s
            """,
            (status, sent_at, notification_id),
        )


def _stale_notifications(
    conn: psycopg.Connection, *, cutoff: datetime
) -> list[dict[str, object]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select id
            from push_notification
            where status in ('queued', 'failed')
              and created_at < %s
              and attempts < %s
            order by created_at, id
            """,
            (cutoff, MAX_PUSH_ATTEMPTS),
        )
        return [dict(row) for row in cur.fetchall()]


def _enqueue_push_job(settings: Settings, notification_id: UUID) -> None:
    from redis import Redis
    from rq import Queue

    queue = Queue(PUSH_QUEUE_NAME, connection=Redis.from_url(settings.redis_url))
    queue.enqueue(
        "procurepilot_api.modules.devices.push_job.process_push_notification",
        str(notification_id),
        job_id=str(notification_id),
    )


if __name__ == "__main__":
    # `sweep_stale_push_notifications()` (T012) was never invoked by anything — no scheduler,
    # cron, or CI/infra entrypoint referenced it (PR review finding, chunk 009-mobile-app-mvp).
    # This codebase has no periodic-job mechanism yet at all (no APScheduler, no rq-scheduler, no
    # cron container) — adding one is an infrastructure/deployment decision, not a bug fix, so
    # this stays deliberately minimal: `python -m procurepilot_api.modules.devices.push_job` runs
    # one sweep pass and exits, so ANY external periodic trigger (a Kubernetes CronJob, a systemd
    # timer, a cron sidecar, an ops runbook) can drive it without this fix picking that mechanism.
    # Wiring an actual recurring trigger is still an open operational task.
    count = sweep_stale_push_notifications()
    logger.info("push notification retry sweep completed", extra={"enqueued": count})
