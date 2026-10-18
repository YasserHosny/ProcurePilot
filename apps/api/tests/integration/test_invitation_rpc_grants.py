"""The invitation RPCs are server-side only — security review 2026-10-18, finding 2.

accept_member_invitation takes the user id and address from its arguments, so through
/rest/v1/rpc the public anon key let any holder of an invitation link redeem it for their own
account. The API calls it over DATABASE_URL after proving the invitee owns the address.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

CALLS = {
    "accept_member_invitation": (
        "select accept_member_invitation(%s, %s::uuid, %s)",
        ("hash", str(uuid4()), "someone@example.test"),
    ),
    "member_invitation_for_token": (
        "select * from member_invitation_for_token(%s)",
        ("hash",),
    ),
}


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("function", sorted(CALLS))
def test_client_roles_cannot_execute_invitation_rpcs(
    conn: psycopg.Connection, role: str, function: str
) -> None:
    sql, params = CALLS[function]
    with conn.cursor() as cur:
        cur.execute(f"set local role {role}")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(sql, params)


def test_server_side_connection_can_execute_accept(conn: psycopg.Connection) -> None:
    """Positive control: an unknown token hash returns null rather than raising."""
    sql, params = CALLS["accept_member_invitation"]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        assert cur.fetchone() == (None,)
