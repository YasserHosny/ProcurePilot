"""Database fixtures and fakes for the feedback integration tests (spec 025).

These need a Postgres with the spec 025 migrations applied (`TEST_DATABASE_URL`). Everything
a test creates is committed (the service opens its own connections) and removed on exit.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace
from integration.smart_compare_helpers import cleanup_workspace, settings_for_test_db
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.service import FeedbackService, SubmitResult
from procurepilot_api.modules.feedback.storage import FeedbackStorage
from procurepilot_api.shared.audit import AuditEventCreate

ALL_ROLES: tuple[MemberRole, ...] = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a local Postgres with the spec 025 migrations",
)


class FakeStorage(FeedbackStorage):
    """In-memory bucket. `fail_on_upload=3` makes the third upload raise."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips FeedbackStorage.__init__
        self.objects: dict[str, bytes] = {}
        self.upload_calls = 0
        self.fail_on_upload: int | None = None
        self.delete_calls: list[list[str]] = []
        self.tokens: list[str] = []

    def upload(self, *, bearer_token: str, path: str, content: bytes, content_type: str) -> None:
        self.upload_calls += 1
        if self.fail_on_upload == self.upload_calls:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"})
        assert path not in self.objects, "upsert=false: an object must never be overwritten"
        self.tokens.append(bearer_token)
        self.objects[path] = content

    def delete(self, paths: Sequence[str]) -> list[str]:
        self.delete_calls.append(list(paths))
        for path in paths:
            self.objects.pop(path, None)
        return []

    def signed_url(self, path: str) -> str:
        if path not in self.objects:
            raise ServiceUnavailableError(details={"dependency": "supabase_storage"})
        return f"http://storage.test/{path}?token=t"


class RecordingAudit:
    """The member-path feedback audit events written since this harness was made.

    The member service appends `feedback.*` events on its own transaction (debate-review F5,
    2026-11-20), so they are read back from `audit_event` rather than captured in memory. Each
    entry is `(event, None)`: there is no bearer token on an in-transaction write.
    """

    def __init__(self) -> None:
        assert TEST_DATABASE_URL
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
            row = conn.execute("select coalesce(max(id), 0) from audit_event").fetchone()
        self._after_id = row[0] if row else 0

    @property
    def events(self) -> list[tuple[AuditEventCreate, str | None]]:
        assert TEST_DATABASE_URL
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None, row_factory=dict_row) as c:
            rows = c.execute(
                "select tenant_id, actor_membership_id, actor_email, action, target, "
                "outcome::text as outcome from audit_event "
                "where id > %s and action in ('feedback.submitted', 'feedback.withdrawn') "
                "order by id",
                (self._after_id,),
            ).fetchall()
        return [(AuditEventCreate.model_validate(row), None) for row in rows]

    def actions(self) -> list[str]:
        return [event.action for event, _ in self.events]


@dataclass
class FeedbackWorld:
    """One workspace with a member per role, and a second workspace for isolation checks."""

    workspace: Workspace
    members: dict[MemberRole, CurrentMember]
    other_workspace: Workspace
    other_owner: CurrentMember
    extra_user_ids: list[UUID] = field(default_factory=list)

    def member(self, role: MemberRole) -> CurrentMember:
        return self.members[role]


def _current_member(
    workspace_tenant: UUID, user_id: UUID, membership_id: UUID, email: str, role: MemberRole
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=workspace_tenant,
        user_id=user_id,
        email=email,
        role=role,
    )


def _add_member(cur: psycopg.Cursor, tenant_id: UUID, role: MemberRole) -> tuple[UUID, UUID, str]:
    user_id, membership_id = uuid4(), uuid4()
    email = f"fb-{role.value}-{user_id.hex[:8]}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role.value),
    )
    return user_id, membership_id, email


@contextmanager
def committed_feedback_world(label: str) -> Iterator[FeedbackWorld]:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    extra_users: list[UUID] = []
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, label, role="owner")
            other = make_workspace(cur, f"{label}-b", role="owner")
            members: dict[MemberRole, CurrentMember] = {
                MemberRole.owner: _current_member(
                    workspace.tenant_id,
                    workspace.user_id,
                    workspace.membership_id,
                    f"{label}-owner@example.test",
                    MemberRole.owner,
                )
            }
            for role in ALL_ROLES:
                if role == MemberRole.owner:
                    continue
                user_id, membership_id, email = _add_member(cur, workspace.tenant_id, role)
                extra_users.append(user_id)
                members[role] = _current_member(
                    workspace.tenant_id, user_id, membership_id, email, role
                )
            other_owner = _current_member(
                other.tenant_id,
                other.user_id,
                other.membership_id,
                f"{label}-b-owner@example.test",
                MemberRole.owner,
            )
        conn.commit()
    try:
        yield FeedbackWorld(workspace, members, other, other_owner, extra_users)
    finally:
        for ws in (workspace, other):
            cleanup_workspace(ws)
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                for user_id in extra_users:
                    cur.execute("delete from auth.users where id = %s", (user_id,))
            conn.commit()


@dataclass
class Harness:
    settings: Settings
    storage: FakeStorage
    audit: RecordingAudit
    service: FeedbackService


def make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cooldown_seconds: int = 0,
    app_version: str = "2026.11.18-test",
) -> Harness:
    """A service wired to the test database, an in-memory bucket and a recording audit writer."""
    monkeypatch.setenv("FEEDBACK_COOLDOWN_SECONDS", str(cooldown_seconds))
    monkeypatch.setenv("APP_VERSION", app_version)
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:4200")
    settings = settings_for_test_db(monkeypatch)
    storage = FakeStorage()
    audit = RecordingAudit()
    return Harness(settings, storage, audit, FeedbackService(settings, storage))


def submit(
    harness: Harness,
    member: CurrentMember,
    *,
    text: str = "Something is off on this page",
    key: UUID | None = None,
    **kwargs: object,
) -> SubmitResult:
    return harness.service.submit(
        member=member,
        bearer_token="member-jwt",
        idempotency_key=key or uuid4(),
        text=text,
        category=kwargs.pop("category", None),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def db_rows(sql: str, params: Sequence[object] = ()) -> list[dict[str, object]]:
    """Read as the database owner, bypassing RLS, to check what is really stored."""
    assert TEST_DATABASE_URL
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def db_execute(sql: str, params: Sequence[object] = (), *, bypass_triggers: bool = False) -> None:
    """Write as the database owner (fixtures only)."""
    assert TEST_DATABASE_URL
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            if bypass_triggers:
                cur.execute("set local session_replication_role = replica")
            cur.execute(sql, params)
        conn.commit()
