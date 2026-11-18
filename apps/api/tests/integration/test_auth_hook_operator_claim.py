"""Access-token hook: `platform_operator` UI-hint claim (spec 025 T063). UNRUN without a database.

The claim is a hint for the web app's navigation only. These tests pin that the hook still
produces exactly the claims the API requires and adds the hint only for ACTIVE operators.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

from integration.catalogue_helpers import Workspace, make_workspace
from integration.feedback_operator_helpers import grant_operator

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def _claims(cur: psycopg.Cursor, workspace: Workspace) -> dict[str, object]:
    cur.execute("reset role")
    cur.execute(
        "select (public.custom_access_token_hook(jsonb_build_object("
        "'user_id', %s::text, 'claims', "
        "jsonb_build_object('role', 'authenticated', 'sub', %s::text)"
        "))) -> 'claims'",
        (workspace.user_id, workspace.user_id),
    )
    row = cur.fetchone()
    assert row is not None
    return row[0]


def test_active_operator_gets_the_hint_and_keeps_the_required_claims(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "hookop")
        grant_operator(cur, ws)
        claims = _claims(cur, ws)
    assert claims["platform_operator"] is True
    assert claims["tenant_id"] == str(ws.tenant_id)
    assert claims["member_role"] == "owner"
    assert claims["role"] == "authenticated", "the Postgres role claim is never touched"


def test_non_operator_gets_no_hint(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "hookplain")
        claims = _claims(cur, ws)
    assert "platform_operator" not in claims
    assert claims["tenant_id"] == str(ws.tenant_id)


def test_revoked_operator_gets_no_hint(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "hookrev")
        grant_operator(cur, ws)
        cur.execute(
            "update platform_operator set revoked_at = now() where user_id = %s", (ws.user_id,)
        )
        claims = _claims(cur, ws)
    assert "platform_operator" not in claims


def test_user_without_a_membership_still_loses_the_workspace_claims(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        # A buyer, not the owner: the owner guard refuses removing a workspace's last owner.
        ws = make_workspace(cur, "hooknomem", role="buyer")
        cur.execute("update membership set status = 'removed' where user_id = %s", (ws.user_id,))
        claims = _claims(cur, ws)
    assert "tenant_id" not in claims and "member_role" not in claims
