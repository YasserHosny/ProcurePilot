"""Feedback background jobs (spec 025, research D9 / D10): operator digest, retention, orphan sweep.

    python -m procurepilot_api.workers.feedback_worker --interval 900
    python -m procurepilot_api.workers.feedback_worker --once

Three independent jobs run on each pass; a failure in one never blocks the others.

* Digest (FR-024): for each ACTIVE operator who opted in, at most one email per UTC day, sent once
  the configured hour has passed, and only if there is feedback newer than the operator's
  `digest_last_sent_at` watermark. The watermark moves only after a successful send, so a failed
  send is retried on the next pass and an empty day sends nothing. The body is rendered by
  `digest_renderer` and carries workspace, category, excerpt and a triage link, never an email
  address or an attachment.
* Retention (FR-023): submissions older than `feedback_retention_months` (12) by `created_at`,
  whatever their status, are deleted together with their stored objects. Objects go first: if
  storage fails, the rows stay and the next pass retries. One aggregate `feedback.retention_purged`
  audit event per pass records counts only, never content, in the same transaction as the delete.
* Orphan sweep: storage objects in the feedback bucket that no attachment row references and that
  are older than an hour (a failed submit or a failed withdrawal cleanup) are removed. The hour is
  the grace period for an upload whose submission transaction has not committed yet.

The worker connects over DATABASE_URL, the trusted server-side connection every worker in this
package uses, and removes objects with the service-role storage client.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from supabase import create_client

from procurepilot_api import db
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.feedback.digest_renderer import DigestItem, render_feedback_digest
from procurepilot_api.modules.feedback.operator_service import DEFAULT_BUCKET, feedback_setting
from procurepilot_api.shared.logging import get_trace_id
from procurepilot_api.shared.mailer import FakeMailer, Mailer, get_mailer

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_MONTHS = 12
DEFAULT_DIGEST_HOUR_UTC = 7  # same as config.feedback_digest_hour_utc
DEFAULT_WEB_URL = "http://localhost:4200"
ORPHAN_GRACE = timedelta(hours=1)
# A submission's created_at is when its transaction began, and that transaction stays open while
# files upload. The digest only takes rows older than this, and moves each operator's watermark
# only this far, so a row still committing is picked up next time rather than skipped forever
# (debate-review F4, 2026-11-20). Requests time out after 120 s (nginx), so 10 minutes is ample.
DIGEST_SETTLE = timedelta(minutes=10)
BATCH_LIMIT = 500
REMOVE_CHUNK = 100


class ObjectRemover(Protocol):
    def remove(self, *, bucket: str, paths: Sequence[str]) -> None: ...


class SupabaseObjectRemover:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def remove(self, *, bucket: str, paths: Sequence[str]) -> None:
        if not paths:
            return
        client = create_client(
            self._settings.supabase_url,
            self._settings.supabase_service_role_key.get_secret_value(),
        )
        for start in range(0, len(paths), REMOVE_CHUNK):
            client.storage.from_(bucket).remove(list(paths[start : start + REMOVE_CHUNK]))


def _audit(conn: psycopg.Connection[Any], *, action: str, target: dict[str, object]) -> None:
    """Append an audit event on the same connection, so it commits with the work it records."""
    conn.execute(
        "select record_audit_event(%s, 'success'::audit_outcome, null, null, %s, %s::jsonb, %s)",
        (action, "feedback_worker", Jsonb(target), get_trace_id()),
    )


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def run_digest(settings: Settings, mailer: Mailer, now: datetime) -> dict[str, int]:
    stats = {"operators": 0, "sent": 0, "skipped_empty": 0, "skipped_not_due": 0, "failed": 0}
    hour = int(feedback_setting(settings, "feedback_digest_hour_utc", DEFAULT_DIGEST_HOUR_UTC))
    if now.hour < hour:
        return stats
    web_url = settings.web_public_url or settings.web_origin or DEFAULT_WEB_URL

    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select user_id, email, digest_locale, digest_last_sent_at "
                "from platform_operator where revoked_at is null and digest_opt_in "
                "order by granted_at, email"
            )
            operators = cur.fetchall()
        stats["operators"] = len(operators)

        for operator in operators:
            last_sent: datetime | None = operator["digest_last_sent_at"]
            if (
                last_sent is not None
                and last_sent.astimezone(UTC).date() >= now.astimezone(UTC).date()
            ):
                stats["skipped_not_due"] += 1
                continue
            since = last_sent or (now - timedelta(days=1))
            settled = now - DIGEST_SETTLE

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select s.category::text as category, s.text_content, s.created_at, "
                    "t.name as workspace_name "
                    "from feedback_submission s join tenant t on t.id = s.tenant_id "
                    "where s.created_at > %s and s.created_at <= %s "
                    "order by s.created_at, s.id",
                    (since, settled),
                )
                rows = cur.fetchall()
            if not rows:
                stats["skipped_empty"] += 1
                continue

            items = [
                DigestItem(
                    workspace_name=row["workspace_name"],
                    category=row["category"],
                    text=row["text_content"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
            subject, html_body, text_body = render_feedback_digest(
                items, operator["digest_locale"], web_url
            )
            try:
                mailer.send(to=operator["email"], subject=subject, body=text_body, html=html_body)
            except Exception:
                logger.exception("Feedback digest send failed; it will be retried next pass")
                stats["failed"] += 1
                continue

            conn.execute(
                "update platform_operator set digest_last_sent_at = %s "
                "where user_id = %s and revoked_at is null",
                (settled, operator["user_id"]),
            )
            conn.commit()
            stats["sent"] += 1
    return stats


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def purge_retention(
    settings: Settings,
    remover: ObjectRemover,
    now: datetime,
) -> dict[str, int]:
    months = int(feedback_setting(settings, "feedback_retention_months", DEFAULT_RETENTION_MONTHS))
    bucket = str(feedback_setting(settings, "feedback_bucket", DEFAULT_BUCKET))
    stats = {"submissions": 0, "objects": 0}

    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select id from feedback_submission "
                "where created_at < %s::timestamptz - make_interval(months => %s) "
                "order by created_at limit %s",
                (now, months, BATCH_LIMIT),
            )
            ids = [row["id"] for row in cur.fetchall()]
            if not ids:
                return stats
            cur.execute(
                "select storage_path from feedback_attachment where submission_id = any(%s)",
                (ids,),
            )
            paths = [row["storage_path"] for row in cur.fetchall()]

        # Objects first. If storage fails the exception leaves every row in place, so the next
        # pass retries instead of orphaning objects that no row points to.
        remover.remove(bucket=bucket, paths=paths)

        deleted = conn.execute("delete from feedback_submission where id = any(%s)", (ids,))
        stats["submissions"] = deleted.rowcount
        stats["objects"] = len(paths)
        _audit(
            conn,
            action="feedback.retention_purged",
            target={
                "submissions": stats["submissions"],
                "objects": stats["objects"],
                "retention_months": months,
            },
        )
        conn.commit()
    return stats


# ---------------------------------------------------------------------------
# Orphan sweep
# ---------------------------------------------------------------------------


def sweep_orphans(settings: Settings, remover: ObjectRemover, now: datetime) -> dict[str, int]:
    bucket = str(feedback_setting(settings, "feedback_bucket", DEFAULT_BUCKET))
    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select o.name from storage.objects o "
                "where o.bucket_id = %s and o.created_at < %s "
                "and not exists "
                "(select 1 from feedback_attachment a where a.storage_path = o.name) "
                "order by o.created_at limit %s",
                (bucket, now - ORPHAN_GRACE, BATCH_LIMIT),
            )
            names = [row["name"] for row in cur.fetchall()]
    remover.remove(bucket=bucket, paths=names)
    return {"orphans_removed": len(names)}


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


def tick(
    settings: Settings,
    *,
    mailer: Mailer | None = None,
    remover: ObjectRemover | None = None,
    now: datetime | None = None,
) -> dict[str, dict[str, int]]:
    moment = now or datetime.now(UTC)
    active_mailer = mailer or get_mailer()
    active_remover = remover or SupabaseObjectRemover(settings)
    results: dict[str, dict[str, int]] = {}
    # The stub mailer "sends" nothing yet would advance digest_last_sent_at, losing the day's
    # digest without a trace. On a real deployment, skip the digest until mail is configured.
    stub_on_deployment = (
        mailer is None and isinstance(active_mailer, FakeMailer) and settings.api_env != "local"
    )
    if stub_on_deployment:
        logger.error(
            "Feedback digest skipped: RFQ_MAILER_MODE is not 'mailgun' on %s, so no email "
            "would be sent. Retention and the orphan sweep still run.",
            settings.api_env,
        )
        results["digest"] = {"skipped_no_mailer": 1}
    jobs: dict[str, Any] = {
        "digest": lambda: run_digest(settings, active_mailer, moment),
        "retention": lambda: purge_retention(settings, active_remover, moment),
        "orphans": lambda: sweep_orphans(settings, active_remover, moment),
    }
    for name, job in jobs.items():
        if name == "digest" and stub_on_deployment:
            continue
        try:
            results[name] = job()
        except Exception:
            logger.exception("Feedback worker job failed: %s", name)
            results[name] = {"failed": 1}
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProcurePilot feedback worker")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=900,
        help="seconds between passes (default: 900)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.api_log_level.upper(), logging.INFO))
    logger.info("Starting ProcurePilot feedback worker (once=%s)", args.once)

    if args.once:
        logger.info("Completed single pass: %s", tick(settings))
        return

    while True:
        try:
            logger.info("Feedback pass completed: %s", tick(settings))
        except Exception:
            logger.exception("Error executing feedback worker tick")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
