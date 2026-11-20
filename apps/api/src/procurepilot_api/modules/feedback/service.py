"""Member and owner feedback service (spec 025).

Every read and write runs on a direct psycopg connection as the `authenticated` role with the
caller's synthesised claims, so row-level security decides what is visible. The service-role
client is used only for storage deletes and signed URLs, after the row check has passed.

One submission is one transaction: files are validated, uploaded, and the submission and
attachment rows are inserted together. Any failure removes what was uploaded.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api import db
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    FeedbackCooldownError,
    FeedbackWithdrawRefusedError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.context import (
    allowed_web_origins,
    locale_from_accept_language,
    page_path_from_referer,
)
from procurepilot_api.modules.feedback.schemas import (
    Attachment,
    Category,
    SignedUrl,
    Status,
    Submission,
    SubmissionPage,
)
from procurepilot_api.modules.feedback.storage import FeedbackStorage, attachment_storage_path
from procurepilot_api.modules.feedback.validation import (
    UploadedFile,
    ValidatedAttachment,
    validate_attachments,
)
from procurepilot_api.shared.logging import get_trace_id, redact

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 2000
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# The tenant-facing column list. `labels` is deliberately absent: operator labels are internal,
# so a tenant read never selects them (defence in depth behind the response model).
_SUBMISSION_COLUMNS = (
    "id, tenant_id, submitter_user_id, submitter_name, member_role, text_content, category, "
    "status, page_path, locale, created_at"
)
_ATTACHMENT_COLUMNS = "id, submission_id, kind, content_type, size_bytes, display_order"


@contextmanager
def _feedback_db(settings: Settings, member: CurrentMember) -> Iterator[psycopg.Connection]:
    """One transaction as `feedback_app` carrying the member's claims.

    `feedback_app` (migration 20261120000100) is the only role with access to the feedback tables,
    and only this API's own DATABASE_URL connection can become it: a token used directly against
    PostgREST arrives as `authenticated` and is refused. Commits on a clean exit.
    """
    try:
        with db.connect(settings.database_url.get_secret_value()) as conn:
            with conn.cursor() as cur:
                claims = {
                    "sub": str(member.user_id),
                    "tenant_id": str(member.tenant_id),
                    "role": "authenticated",
                    "member_role": member.role.value,
                }
                cur.execute("set local role feedback_app")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps(claims),),
                )
            yield conn
    except psycopg.Error as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def _audit_in_transaction(
    conn: psycopg.Connection,
    member: CurrentMember,
    action: str,
    target: dict[str, object],
) -> None:
    """Append an audit event on the caller's own transaction.

    It commits or rolls back with the change it describes, so a change is never left without its
    event and a replay never needs to repair one (debate-review F5, 2026-11-20). Goes through the
    same append-only `record_audit_event` function as every other audit write.
    """
    conn.execute(
        "select record_audit_event(%s, 'success'::audit_outcome, %s::uuid, %s::uuid, %s, "
        "%s::jsonb, %s)",
        (
            action,
            str(member.tenant_id),
            str(member.membership_id),
            member.email,
            Jsonb(redact(target)),
            get_trace_id(),
        ),
    )


class _DuplicateIdempotencyKey(Exception):
    """Raised inside the transaction when the (tenant, key) unique index fires."""


@dataclass(frozen=True)
class SubmitResult:
    submission: Submission
    created: bool


def normalise_text(text: str | None) -> str:
    value = (text or "").strip()
    if not value:
        raise UnprocessableEntityError(details={"reason": "text_required", "field": "text"})
    if len(value) > MAX_TEXT_CHARS:
        raise UnprocessableEntityError(
            details={"reason": "text_too_long", "field": "text", "max": MAX_TEXT_CHARS}
        )
    return value


class FeedbackService:
    def __init__(
        self,
        settings: Settings | None = None,
        storage: FeedbackStorage | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage = storage or FeedbackStorage(self._settings)

    # ------------------------------------------------------------------ submit

    def submit(
        self,
        *,
        member: CurrentMember,
        bearer_token: str,
        idempotency_key: UUID,
        text: str | None,
        category: Category | None,
        images: Sequence[UploadedFile] = (),
        audio: UploadedFile | None = None,
        referer: str | None = None,
        accept_language: str | None = None,
    ) -> SubmitResult:
        value = normalise_text(text)
        attachments = validate_attachments(images, audio, self._settings)

        submission_id = uuid4()
        uploaded: list[str] = []
        try:
            with _feedback_db(self._settings, member) as conn:
                # One submission at a time per member: the replay and cooldown checks below read
                # state that a parallel request would change.
                self._lock_member(conn, member)
                replay = self._find_replay(conn, member, idempotency_key)
                if replay is not None:
                    return SubmitResult(replay, created=False)
                self._check_cooldown(conn, member)
                context = self._load_context(conn, member)
                page_path = page_path_from_referer(referer, allowed_web_origins(self._settings))
                locale = locale_from_accept_language(accept_language, context["default_locale"])

                stored: list[tuple[ValidatedAttachment, str, UUID]] = []
                for attachment in attachments:
                    path = attachment_storage_path(
                        tenant_id=member.tenant_id,
                        submission_id=submission_id,
                        filename=attachment.filename,
                    )
                    self._storage.upload(
                        bearer_token=bearer_token,
                        path=path,
                        content=attachment.content,
                        content_type=attachment.content_type,
                    )
                    uploaded.append(path)
                    stored.append((attachment, path, uuid4()))

                row = self._insert_submission(
                    conn,
                    member=member,
                    submission_id=submission_id,
                    idempotency_key=idempotency_key,
                    text=value,
                    category=category,
                    context=context,
                    page_path=page_path,
                    locale=locale,
                )
                attachment_rows = self._insert_attachments(conn, member, submission_id, stored)
                _audit_in_transaction(
                    conn,
                    member,
                    "feedback.submitted",
                    {
                        "submission_id": str(submission_id),
                        "category": category.value if category else None,
                        "image_count": sum(1 for a in attachments if a.kind == "image"),
                        "has_audio": any(a.kind == "audio" for a in attachments),
                    },
                )
        except _DuplicateIdempotencyKey:
            # The key is already used by someone else in this workspace; the member's own earlier
            # use is a replay, handled above under the lock.
            self._storage.delete(uploaded)
            raise ConflictError(details={"reason": "idempotency_key_reused"}) from None
        except BaseException:
            self._storage.delete(uploaded)
            raise

        submission = _to_submission(row, attachment_rows, viewer_user_id=member.user_id)
        return SubmitResult(submission, created=True)

    @staticmethod
    def _lock_member(conn: psycopg.Connection, member: CurrentMember) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"feedback:{member.tenant_id}:{member.user_id}",),
            )

    @staticmethod
    def _find_replay(
        conn: psycopg.Connection, member: CurrentMember, key: UUID
    ) -> Submission | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"select {_SUBMISSION_COLUMNS} from feedback_submission "
                "where tenant_id = %s and idempotency_key = %s and submitter_user_id = %s",
                (member.tenant_id, key, member.user_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        attachments = _fetch_attachments(conn, [row["id"]])
        return _to_submission(row, attachments.get(row["id"], []), viewer_user_id=member.user_id)

    def _check_cooldown(self, conn: psycopg.Connection, member: CurrentMember) -> None:
        cooldown = self._settings.feedback_cooldown_seconds
        if cooldown <= 0:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                select ceil(%s - extract(epoch from (clock_timestamp() - created_at)))::int
                from feedback_submission
                where tenant_id = %s and submitter_user_id = %s
                order by created_at desc
                limit 1
                """,
                (cooldown, member.tenant_id, member.user_id),
            )
            row = cur.fetchone()
        if row is not None and row[0] is not None and row[0] > 0:
            raise FeedbackCooldownError(retry_after_seconds=int(row[0]))

    def _load_context(self, conn: psycopg.Connection, member: CurrentMember) -> dict[str, object]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select t.is_demo, t.default_locale, m.display_name "
                "from tenant t join membership m on m.tenant_id = t.id "
                "where t.id = %s and m.id = %s",
                (member.tenant_id, member.membership_id),
            )
            row = cur.fetchone()
        if row is None:
            # The live membership check passed a moment ago, so this is a race with removal.
            raise NotFoundError(details={"resource": "membership"})
        name = (row["display_name"] or "").strip() or member.email
        return {
            "is_demo": bool(row["is_demo"]),
            "default_locale": row["default_locale"],
            "name": name,
        }

    def _insert_submission(
        self,
        conn: psycopg.Connection,
        *,
        member: CurrentMember,
        submission_id: UUID,
        idempotency_key: UUID,
        text: str,
        category: Category | None,
        context: dict[str, object],
        page_path: str,
        locale: str,
    ) -> dict[str, object]:
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    insert into feedback_submission
                      (id, tenant_id, submitter_user_id, submitter_membership_id, submitter_name,
                       submitter_email, member_role, text_content, category, page_path,
                       app_version, locale, is_demo, idempotency_key)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::feedback_category, %s, %s, %s,
                            %s, %s)
                    returning {_SUBMISSION_COLUMNS}
                    """,
                    (
                        submission_id,
                        member.tenant_id,
                        member.user_id,
                        member.membership_id,
                        context["name"],
                        member.email,
                        member.role.value,
                        text,
                        category.value if category else None,
                        page_path,
                        self._settings.app_version,
                        locale,
                        context["is_demo"],
                        idempotency_key,
                    ),
                )
                row = cur.fetchone()
        except pg_errors.UniqueViolation as exc:
            # The id is a fresh uuid4, so the only unique index this can trip is
            # (tenant_id, idempotency_key): the same key from a parallel or foreign request.
            raise _DuplicateIdempotencyKey from exc
        if row is None:
            raise NotFoundError(details={"resource": "feedback"})
        return row

    def _insert_attachments(
        self,
        conn: psycopg.Connection,
        member: CurrentMember,
        submission_id: UUID,
        stored: Sequence[tuple[ValidatedAttachment, str, UUID]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        with conn.cursor(row_factory=dict_row) as cur:
            for attachment, path, attachment_id in stored:
                cur.execute(
                    f"""
                    insert into feedback_attachment
                      (id, tenant_id, submission_id, kind, storage_path, content_type, size_bytes,
                       display_order)
                    values (%s, %s, %s, %s::feedback_attachment_kind, %s, %s, %s, %s)
                    returning {_ATTACHMENT_COLUMNS}
                    """,
                    (
                        attachment_id,
                        member.tenant_id,
                        submission_id,
                        attachment.kind,
                        path,
                        attachment.content_type,
                        attachment.size_bytes,
                        attachment.display_order,
                    ),
                )
                inserted = cur.fetchone()
                if inserted is not None:
                    rows.append(inserted)
        return rows

    # ------------------------------------------------------------------- reads

    def list_mine(
        self, *, member: CurrentMember, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> SubmissionPage:
        return self._list(member, own_only=True, cursor=cursor, limit=limit)

    def list_workspace(
        self,
        *,
        member: CurrentMember,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        status: Status | None = None,
        category: Category | None = None,
    ) -> SubmissionPage:
        # The router answers 404 first; this keeps the rule in the service too. Row-level
        # security would return only the caller's own rows to a non-owner anyway.
        if member.role != MemberRole.owner:
            raise NotFoundError(details={"resource": "feedback"})
        return self._list(
            member, own_only=False, cursor=cursor, limit=limit, status=status, category=category
        )

    def _list(
        self,
        member: CurrentMember,
        *,
        own_only: bool,
        cursor: str | None,
        limit: int,
        status: Status | None = None,
        category: Category | None = None,
    ) -> SubmissionPage:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        clauses = ["tenant_id = %s"]
        params: list[object] = [member.tenant_id]
        if own_only:
            clauses.append("submitter_user_id = %s")
            params.append(member.user_id)
        if status is not None:
            clauses.append("status = %s::feedback_status")
            params.append(status.value)
        if category is not None:
            clauses.append("category = %s::feedback_category")
            params.append(category.value)
        decoded = decode_cursor(cursor)
        if decoded is not None:
            clauses.append("(created_at, id) < (%s, %s)")
            params.extend(decoded)
        params.append(limit + 1)
        with _feedback_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"select {_SUBMISSION_COLUMNS} from feedback_submission "
                    f"where {' and '.join(clauses)} order by created_at desc, id desc limit %s",
                    params,
                )
                rows = cur.fetchall()
            visible = rows[:limit]
            attachments = _fetch_attachments(conn, [row["id"] for row in visible])
        items = [
            _to_submission(
                row,
                attachments.get(row["id"], []),
                viewer_user_id=member.user_id,
                include_name=not own_only,
            )
            for row in visible
        ]
        next_cursor = (
            encode_cursor(visible[-1]["created_at"], visible[-1]["id"])
            if len(rows) > limit
            else None
        )
        return SubmissionPage(items=items, next_cursor=next_cursor)

    def get(self, *, member: CurrentMember, submission_id: UUID) -> Submission:
        with _feedback_db(self._settings, member) as conn:
            row = _fetch_visible_row(conn, member, submission_id)
            if row is None:
                raise NotFoundError(details={"resource": "feedback"})
            attachments = _fetch_attachments(conn, [row["id"]])
        return _to_submission(
            row,
            attachments.get(row["id"], []),
            viewer_user_id=member.user_id,
            include_name=member.role == MemberRole.owner,
        )

    # ---------------------------------------------------------------- withdraw

    def withdraw(self, *, member: CurrentMember, bearer_token: str, submission_id: UUID) -> None:
        paths: list[str] = []
        with _feedback_db(self._settings, member) as conn:
            with conn.cursor() as cur:
                # Read the object paths first: the delete cascades the attachment rows away. A
                # row that is not the caller's own is invisible or undeletable, handled below.
                cur.execute(
                    "select a.storage_path from feedback_attachment a "
                    "join feedback_submission s on s.id = a.submission_id "
                    "and s.tenant_id = a.tenant_id "
                    "where a.submission_id = %s and a.tenant_id = %s "
                    "and s.submitter_user_id = %s and s.status = 'new'",
                    (submission_id, member.tenant_id, member.user_id),
                )
                paths = [str(row[0]) for row in cur.fetchall()]
                # Atomic against an operator status change: the status test is in the statement,
                # so a concurrent move past `new` makes this match zero rows.
                cur.execute(
                    "delete from feedback_submission "
                    "where id = %s and tenant_id = %s and submitter_user_id = %s "
                    "and status = 'new' returning id",
                    (submission_id, member.tenant_id, member.user_id),
                )
                deleted = cur.fetchone()
            if deleted is None:
                row = _fetch_visible_row(conn, member, submission_id)
                if row is None or row["submitter_user_id"] != member.user_id:
                    # Missing, another workspace, or someone else's (even for the owner): 404.
                    raise NotFoundError(details={"resource": "feedback"})
                raise FeedbackWithdrawRefusedError(details={"status": str(row["status"])})
            _audit_in_transaction(
                conn, member, "feedback.withdrawn", {"submission_id": str(submission_id)}
            )
        self._storage.delete(paths)

    # ------------------------------------------------------------- attachments

    def attachment_url(
        self, *, member: CurrentMember, submission_id: UUID, attachment_id: UUID
    ) -> SignedUrl:
        with _feedback_db(self._settings, member) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select storage_path from feedback_attachment "
                    "where id = %s and submission_id = %s and tenant_id = %s",
                    (attachment_id, submission_id, member.tenant_id),
                )
                row = cur.fetchone()
        if row is None:
            raise NotFoundError(details={"resource": "feedback_attachment"})
        return SignedUrl(
            url=self._storage.signed_url(str(row[0])),
            expires_in=self._settings.feedback_attachment_url_ttl_seconds,
        )

    # ------------------------------------------------------------------- audit


def get_feedback_service() -> FeedbackService:
    return FeedbackService()


# ---------------------------------------------------------------------- helpers


def _fetch_visible_row(
    conn: psycopg.Connection, member: CurrentMember, submission_id: UUID
) -> dict[str, object] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"select {_SUBMISSION_COLUMNS} from feedback_submission "
            "where id = %s and tenant_id = %s",
            (submission_id, member.tenant_id),
        )
        return cur.fetchone()


def _fetch_attachments(
    conn: psycopg.Connection, submission_ids: Sequence[object]
) -> dict[object, list[dict[str, object]]]:
    grouped: dict[object, list[dict[str, object]]] = {}
    if not submission_ids:
        return grouped
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"select {_ATTACHMENT_COLUMNS} from feedback_attachment "
            "where submission_id = any(%s) order by kind, display_order",
            (list(submission_ids),),
        )
        for row in cur.fetchall():
            grouped.setdefault(row["submission_id"], []).append(row)
    return grouped


def _to_submission(
    row: dict[str, object],
    attachment_rows: Sequence[dict[str, object]],
    *,
    viewer_user_id: UUID,
    include_name: bool = False,
) -> Submission:
    own_and_new = row["submitter_user_id"] == viewer_user_id and row["status"] == "new"
    return Submission(
        id=row["id"],  # type: ignore[arg-type]
        text=str(row["text_content"]),
        category=Category(str(row["category"])) if row["category"] is not None else None,
        status=Status(str(row["status"])),
        submitter_name=str(row["submitter_name"]) if include_name else None,
        member_role=MemberRole(str(row["member_role"])),
        page_path=str(row["page_path"]),
        locale=row["locale"],  # type: ignore[arg-type]
        created_at=row["created_at"],  # type: ignore[arg-type]
        can_withdraw=own_and_new,
        attachments=[
            Attachment(
                id=a["id"],  # type: ignore[arg-type]
                kind=a["kind"],  # type: ignore[arg-type]
                content_type=str(a["content_type"]),
                size_bytes=int(a["size_bytes"]),  # type: ignore[call-overload]
                display_order=int(a["display_order"]),  # type: ignore[call-overload]
            )
            for a in attachment_rows
        ],
    )


def encode_cursor(created_at: datetime, submission_id: object) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(submission_id)}, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        submission_id = UUID(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at, submission_id
