"""Platform-operator feedback triage (spec 025, US5, research D2 / D7 / D8).

Everything here runs through `operator_connection`: the direct-psycopg-with-claims path as the
`authenticated` role. What an operator may do is therefore decided by the database (the operator
RLS policies on `feedback_submission` and `feedback_attachment`, the column-level update grant and
the forward-only status trigger), and this module adds only the pre-checks that let it answer with
a precise error. It never uses the service-role connection for a read or a write of feedback rows.
The one service-role call is signing a storage URL, after the row check has passed.

Audit (research D8): list access is ONE aggregate event per request with the filters and the result
count, carrying no tenant; a detail view, a status or label change and an attachment URL each write
an event tagged with the submission's own tenant. Events are written BEFORE the data is released
(reads) or before the transaction commits (writes), so a failed audit write means the operator saw
or changed nothing. Audit targets never hold feedback text or labels: tenants can read audit rows
about their own workspace, and labels are internal.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from supabase import create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import (
    FeedbackInvalidTransitionError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.operator import CurrentOperator, operator_connection
from procurepilot_api.modules.feedback.operator_schemas import (
    FeedbackCategory,
    FeedbackStatus,
    OperatorAttachment,
    OperatorMe,
    OperatorSubmission,
    OperatorSubmissionPage,
    SignedUrl,
)
from procurepilot_api.shared.audit import AuditEventCreate, AuditWriter

DEFAULT_BUCKET = "feedback-attachments"
DEFAULT_URL_TTL_SECONDS = 300


# ---------------------------------------------------------------------------
# Status machine: new -> reviewed -> resolved, or new -> resolved. Never backwards.
# The BEFORE UPDATE trigger enforces the same table; this is the pre-check.
# ---------------------------------------------------------------------------

_FORWARD: dict[FeedbackStatus, frozenset[FeedbackStatus]] = {
    FeedbackStatus.new: frozenset({FeedbackStatus.reviewed, FeedbackStatus.resolved}),
    FeedbackStatus.reviewed: frozenset({FeedbackStatus.resolved}),
    FeedbackStatus.resolved: frozenset(),
}


def is_valid_transition(current: FeedbackStatus, target: FeedbackStatus) -> bool:
    """True for a forward move or for repeating the current status (a labels-only change)."""
    return target == current or target in _FORWARD[current]


def assert_valid_transition(current: FeedbackStatus, target: FeedbackStatus) -> None:
    if not is_valid_transition(current, target):
        raise FeedbackInvalidTransitionError(
            details={"from": current.value, "to": target.value},
        )


# ---------------------------------------------------------------------------
# Cursor: keyset on (created_at desc, id desc)
# ---------------------------------------------------------------------------


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(row_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_raw, id_raw = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(created_raw), UUID(id_raw)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"field": "cursor"}) from exc


# ---------------------------------------------------------------------------
# Storage signing (service role, after the row check)
# ---------------------------------------------------------------------------


class AttachmentSigner(Protocol):
    def sign(self, *, bucket: str, path: str, expires_in: int) -> str: ...


class SupabaseAttachmentSigner:
    """Signs a private-bucket object URL. The only service-role use in the operator path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def sign(self, *, bucket: str, path: str, expires_in: int) -> str:
        try:
            client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
            result = client.storage.from_(bucket).create_signed_url(path, expires_in=expires_in)
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"}) from exc
        return str(result["signedURL"])


def feedback_setting[T](settings: object, name: str, default: T) -> T:
    """Read a `feedback_*` setting, falling back to the documented default.

    The settings are added to `config.py` by the member-API work (T001); the fallback keeps this
    module and the worker usable on a tree where they are not merged yet.
    """
    return getattr(settings, name, default)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SUBMISSION_COLUMNS = """
    s.id, s.tenant_id, s.text_content, s.category::text as category, s.status::text as status,
    s.submitter_name, s.submitter_email, s.member_role, s.page_path, s.locale, s.created_at,
    s.labels, s.app_version, s.is_demo, s.status_changed_at
"""


class OperatorFeedbackService:
    def __init__(
        self,
        settings: Settings | None = None,
        audit_writer: AuditWriter | None = None,
        signer: AttachmentSigner | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._audit = audit_writer or AuditWriter(self._settings)
        self._signer = signer or SupabaseAttachmentSigner(self._settings)

    # -- list -------------------------------------------------------------------------------

    def list_feedback(
        self,
        operator: CurrentOperator,
        *,
        status: FeedbackStatus | None = None,
        category: FeedbackCategory | None = None,
        tenant_id: UUID | None = None,
        is_demo: bool | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> OperatorSubmissionPage:
        limit = max(1, min(limit, 100))
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("s.status = %s::feedback_status")
            params.append(status.value)
        if category is not None:
            clauses.append("s.category = %s::feedback_category")
            params.append(category.value)
        if tenant_id is not None:
            # A filter inside the operator's authorised scope, not a tenancy mechanism.
            clauses.append("s.tenant_id = %s")
            params.append(tenant_id)
        if is_demo is not None:
            clauses.append("s.is_demo = %s")
            params.append(is_demo)
        if cursor is not None:
            created_at, row_id = decode_cursor(cursor)
            clauses.append("(s.created_at, s.id) < (%s, %s)")
            params.extend([created_at, row_id])
        where = f"where {' and '.join(clauses)}" if clauses else ""

        with operator_connection(self._settings, operator) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"select {_SUBMISSION_COLUMNS} from feedback_submission s {where} "  # noqa: S608
                    "order by s.created_at desc, s.id desc limit %s",
                    (*params, limit + 1),
                )
                rows = cur.fetchall()
            page_rows = rows[:limit]
            items = self._hydrate(conn, page_rows)

            self._audit.record(
                AuditEventCreate(
                    tenant_id=None,
                    actor_membership_id=operator.membership_id,
                    actor_email=operator.email,
                    action="feedback.operator_listed",
                    target={
                        "filters": {
                            "status": status.value if status else None,
                            "category": category.value if category else None,
                            "tenant_id": str(tenant_id) if tenant_id else None,
                            "is_demo": is_demo,
                        },
                        "result_count": len(items),
                    },
                    outcome="success",
                )
            )

        next_cursor = None
        if len(rows) > limit and page_rows:
            last = page_rows[-1]
            next_cursor = encode_cursor(last["created_at"], last["id"])
        return OperatorSubmissionPage(items=items, next_cursor=next_cursor)

    # -- detail -----------------------------------------------------------------------------

    def get_feedback(self, operator: CurrentOperator, submission_id: UUID) -> OperatorSubmission:
        with operator_connection(self._settings, operator) as conn:
            row = self._fetch_one(conn, submission_id)
            item = self._hydrate(conn, [row])[0]
            self._audit.record(
                AuditEventCreate(
                    tenant_id=item.tenant_id,
                    actor_membership_id=operator.membership_id,
                    actor_email=operator.email,
                    action="feedback.operator_viewed",
                    target={"submission_id": str(item.id)},
                    outcome="success",
                )
            )
        return item

    # -- status and labels --------------------------------------------------------------------

    def update_feedback(
        self,
        operator: CurrentOperator,
        submission_id: UUID,
        *,
        status: FeedbackStatus | None,
        labels: Sequence[str] | None,
    ) -> OperatorSubmission:
        with operator_connection(self._settings, operator) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # `for update` serialises a concurrent operator change and a member withdrawal.
                cur.execute(
                    "select tenant_id, status::text as status, labels "
                    "from feedback_submission where id = %s for update",
                    (submission_id,),
                )
                current = cur.fetchone()
            if current is None:
                raise NotFoundError(details={"resource": "feedback"})

            tenant_id: UUID = current["tenant_id"]
            current_status = FeedbackStatus(current["status"])
            status_changes = status is not None and status != current_status
            if status is not None:
                assert_valid_transition(current_status, status)
            labels_change = labels is not None and list(labels) != list(current["labels"])

            sets: list[str] = []
            params: list[object] = []
            if status_changes and status is not None:
                sets.append("status = %s::feedback_status")
                params.append(status.value)
            if labels_change and labels is not None:
                sets.append("labels = %s")
                params.append(list(labels))

            if sets:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"update feedback_submission set {', '.join(sets)} "  # noqa: S608
                            "where id = %s",
                            (*params, submission_id),
                        )
                except (pg_errors.RaiseException, pg_errors.CheckViolation) as exc:
                    # The trigger is the authority: a race or a path that skipped the pre-check.
                    if status is None:
                        raise
                    raise FeedbackInvalidTransitionError(
                        details={"from": current_status.value, "to": status.value}
                    ) from exc

            if status_changes and status is not None:
                self._audit.record(
                    AuditEventCreate(
                        tenant_id=tenant_id,
                        actor_membership_id=operator.membership_id,
                        actor_email=operator.email,
                        action="feedback.operator_status_changed",
                        target={
                            "submission_id": str(submission_id),
                            "from": current_status.value,
                            "to": status.value,
                        },
                        outcome="success",
                    )
                )
            if labels_change and labels is not None:
                self._audit.record(
                    AuditEventCreate(
                        tenant_id=tenant_id,
                        actor_membership_id=operator.membership_id,
                        actor_email=operator.email,
                        action="feedback.operator_labels_changed",
                        # Counts only: labels are internal and audit rows are tenant-readable.
                        target={"submission_id": str(submission_id), "label_count": len(labels)},
                        outcome="success",
                    )
                )

            row = self._fetch_one(conn, submission_id)
            return self._hydrate(conn, [row])[0]

    # -- attachment URL -----------------------------------------------------------------------

    def attachment_url(
        self,
        operator: CurrentOperator,
        submission_id: UUID,
        attachment_id: UUID,
    ) -> SignedUrl:
        with operator_connection(self._settings, operator) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # The operator RLS policy on feedback_attachment is the access check.
                cur.execute(
                    "select a.storage_path, a.tenant_id from feedback_attachment a "
                    "where a.id = %s and a.submission_id = %s",
                    (attachment_id, submission_id),
                )
                row = cur.fetchone()
            if row is None:
                raise NotFoundError(details={"resource": "attachment"})

            self._audit.record(
                AuditEventCreate(
                    tenant_id=row["tenant_id"],
                    actor_membership_id=operator.membership_id,
                    actor_email=operator.email,
                    action="feedback.operator_attachment_url_issued",
                    target={
                        "submission_id": str(submission_id),
                        "attachment_id": str(attachment_id),
                    },
                    outcome="success",
                )
            )

        ttl = int(
            feedback_setting(
                self._settings, "feedback_attachment_url_ttl_seconds", DEFAULT_URL_TTL_SECONDS
            )
        )
        bucket = str(feedback_setting(self._settings, "feedback_bucket", DEFAULT_BUCKET))
        url = self._signer.sign(bucket=bucket, path=row["storage_path"], expires_in=ttl)
        return SignedUrl(url=url, expires_in=ttl)

    # -- operator profile and digest preference ----------------------------------------------

    def me(self, operator: CurrentOperator) -> OperatorMe:
        with operator_connection(self._settings, operator) as conn:
            row = conn.execute(
                "select digest_opt_in, digest_locale from operator_digest_preference()"
            ).fetchone()
        if row is None:
            # Revoked between the dependency check and here.
            raise NotFoundError()
        return OperatorMe(digest_enabled=bool(row[0]), digest_locale=row[1])

    def set_digest_preference(
        self,
        operator: CurrentOperator,
        *,
        enabled: bool,
        locale: str | None,
    ) -> OperatorMe:
        with operator_connection(self._settings, operator) as conn:
            row = conn.execute(
                "select digest_opt_in, digest_locale from set_operator_digest_preference(%s, %s)",
                (enabled, locale),
            ).fetchone()
            if row is None:
                raise NotFoundError()
            self._audit.record(
                AuditEventCreate(
                    tenant_id=operator.tenant_id,
                    actor_membership_id=operator.membership_id,
                    actor_email=operator.email,
                    action="feedback.digest_preference_changed",
                    target={"enabled": bool(row[0]), "locale": row[1]},
                    outcome="success",
                )
            )
        return OperatorMe(digest_enabled=bool(row[0]), digest_locale=row[1])

    # -- internals ----------------------------------------------------------------------------

    @staticmethod
    def _fetch_one(conn: psycopg.Connection[Any], submission_id: UUID) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"select {_SUBMISSION_COLUMNS} from feedback_submission s "  # noqa: S608
                "where s.id = %s",
                (submission_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "feedback"})
        return row

    @staticmethod
    def _hydrate(
        conn: psycopg.Connection[Any],
        rows: Sequence[Mapping[str, Any]],
    ) -> list[OperatorSubmission]:
        """Attach attachments and workspace names to submission rows (two batched queries)."""
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        tenant_ids = sorted({row["tenant_id"] for row in rows}, key=str)

        attachments: dict[UUID, list[OperatorAttachment]] = {}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select id, submission_id, kind::text as kind, content_type, size_bytes, "
                "display_order from feedback_attachment where submission_id = any(%s) "
                "order by submission_id, kind, display_order",
                (ids,),
            )
            for att in cur.fetchall():
                attachments.setdefault(att["submission_id"], []).append(
                    OperatorAttachment(
                        id=att["id"],
                        kind=att["kind"],
                        content_type=att["content_type"],
                        size_bytes=att["size_bytes"],
                        display_order=att["display_order"],
                    )
                )
            cur.execute(
                "select tenant_id, tenant_name from operator_tenant_names(%s::uuid[])",
                (tenant_ids,),
            )
            names = {name["tenant_id"]: name["tenant_name"] for name in cur.fetchall()}

        return [
            OperatorSubmission(
                id=row["id"],
                tenant_id=row["tenant_id"],
                tenant_name=names.get(row["tenant_id"]),
                text=row["text_content"],
                category=row["category"],
                status=row["status"],
                submitter_name=row["submitter_name"],
                submitter_email=row["submitter_email"],
                member_role=row["member_role"],
                page_path=row["page_path"],
                locale=row["locale"],
                created_at=row["created_at"],
                labels=list(row["labels"] or []),
                app_version=row["app_version"],
                is_demo=row["is_demo"],
                status_changed_at=row["status_changed_at"],
                attachments=attachments.get(row["id"], []),
            )
            for row in rows
        ]


def get_operator_feedback_service() -> OperatorFeedbackService:
    return OperatorFeedbackService()
