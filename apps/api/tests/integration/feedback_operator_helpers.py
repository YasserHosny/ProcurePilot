"""Fixtures shared by the platform-operator feedback tests (spec 025, US5).

Two flavours of test need two flavours of data:

* RLS and trigger tests run inside one rolled-back transaction as the real `authenticated` role
  (`act_as`), so they use the in-transaction helpers.
* Service, worker and CLI tests open their own connections, so the rows they read must be
  committed. `committed_workspace` creates them and removes them again on exit. `audit_event` is
  append-only, so audit rows from those runs stay; every test filters by its own ids.

Schema assumptions come from specs/025-user-feedback/data-model.md: `platform_operator`,
`feedback_submission`, `feedback_attachment`, and the `feedback-attachments` bucket.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

import psycopg

from integration.catalogue_helpers import (
    Workspace,
    act_as,
    delete_tenant_scoped_rows,
    make_workspace,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def act_as_feedback_app(cur: psycopg.Cursor, workspace: Workspace) -> None:
    """Act as `workspace`'s member the way the API does for feedback: role `feedback_app`.

    `act_as` (role `authenticated`) is the PostgREST path, which has no feedback-table access
    since migration 20261120000100.
    """
    cur.execute("set local role feedback_app")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (workspace.claims(),))


__all__ = [
    "TEST_DATABASE_URL",
    "Workspace",
    "act_as",
    "act_as_feedback_app",
    "committed_workspace",
    "grant_operator",
    "insert_attachment",
    "insert_submission",
    "make_workspace",
    "operator_member",
]


def grant_operator(
    cur: psycopg.Cursor, workspace: Workspace, *, digest_opt_in: bool = False
) -> None:
    """Make the workspace's user an active platform operator. Runs as the table owner."""
    cur.execute("reset role")
    cur.execute(
        "insert into platform_operator (user_id, email, granted_by, digest_opt_in) "
        "values (%s, %s, 'tests', %s) "
        "on conflict (user_id) do update "
        "set revoked_at = null, digest_opt_in = excluded.digest_opt_in",
        (workspace.user_id, f"op-{workspace.user_id.hex[:10]}@example.test", digest_opt_in),
    )


def insert_submission(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    text: str = "something is off on this page",
    category: str | None = "bug",
    status: str = "new",
    created_at: datetime | None = None,
    is_demo: bool = False,
    locale: str = "en",
) -> UUID:
    """Insert a submission as the table owner (RLS bypassed), the way the API would have."""
    submission_id = uuid4()
    cur.execute("reset role")
    cur.execute(
        """
        insert into feedback_submission (
          id, tenant_id, submitter_user_id, submitter_membership_id, submitter_name,
          submitter_email, member_role, text_content, category, status, page_path, app_version,
          locale, is_demo, idempotency_key, created_at
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s::feedback_category, 'new', %s, %s, %s, %s, %s,
                  coalesce(%s, now()))
        """,
        (
            submission_id,
            workspace.tenant_id,
            workspace.user_id,
            workspace.membership_id,
            f"{workspace.label} Submitter",
            f"{workspace.label.lower()}-submitter@example.test",
            workspace.role,
            text,
            category,
            "/requests?tab=open",
            "test-build",
            locale,
            is_demo,
            uuid4(),
            created_at,
        ),
    )
    if status != "new":
        # The status trigger only moves forward, so step through it as the owner would.
        cur.execute(
            "update feedback_submission set status = %s::feedback_status where id = %s",
            (status, submission_id),
        )
    return submission_id


def insert_attachment(
    cur: psycopg.Cursor,
    workspace: Workspace,
    submission_id: UUID,
    *,
    kind: str = "image",
    display_order: int = 0,
    storage_path: str | None = None,
) -> tuple[UUID, str]:
    attachment_id = uuid4()
    path = storage_path or (
        f"tenants/{workspace.tenant_id}/feedback/{submission_id}/{attachment_id}/shot.png"
    )
    cur.execute("reset role")
    cur.execute(
        "insert into feedback_attachment (id, tenant_id, submission_id, kind, storage_path, "
        "content_type, size_bytes, display_order) "
        "values (%s, %s, %s, %s::feedback_attachment_kind, %s, %s, 1024, %s)",
        (
            attachment_id,
            workspace.tenant_id,
            submission_id,
            kind,
            path,
            "image/png" if kind == "image" else "audio/webm",
            display_order,
        ),
    )
    return attachment_id, path


@contextmanager
def committed_workspace(label: str, *, role: str = "owner") -> Iterator[Workspace]:
    """A workspace committed to the database for tests that cross connections. Cleans up on exit."""
    with psycopg.connect(TEST_DATABASE_URL or "", autocommit=False) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, label, role=role)
        conn.commit()
    try:
        yield workspace
    finally:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                # Tenant-scoped rows first (it handles FK order), then the tenant and the user.
                delete_tenant_scoped_rows(cur, workspace.tenant_id)
                cur.execute(
                    "delete from platform_operator where user_id = %s", (workspace.user_id,)
                )
                cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
                cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
            conn.commit()


def operator_member(workspace: Workspace) -> object:
    """The CurrentMember the (patched) JWT step would resolve for this workspace's user."""
    from procurepilot_api.deps import CurrentMember
    from procurepilot_api.modules.auth.jwt import MemberRole

    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}-{workspace.role}@example.test",
        role=MemberRole(workspace.role),
    )
