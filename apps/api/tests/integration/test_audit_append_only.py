"""audit_event is append-only, and the audit writer cannot forge tenancy — task T035.

These run against a real Postgres with the migrations applied. The guarantees under test live in
the database, so testing them against a mock would prove nothing at all.

Set TEST_DATABASE_URL to a database with migrations 0001-0007 applied. Skipped when unset, so a
developer without a database can still run the rest of the suite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

TENANT_A = "aaaaaaaa-1111-1111-1111-111111111111"
TENANT_B = "bbbbbbbb-2222-2222-2222-222222222222"


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def act_as_member(cur: psycopg.Cursor, tenant_id: str) -> None:
    """Become the `authenticated` role carrying a tenant claim, as a real request would."""
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (f'{{"tenant_id":"{tenant_id}","role":"authenticated","member_role":"owner"}}',),
    )


def test_authenticated_cannot_update_an_audit_event(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, TENANT_A)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("update audit_event set action = 'tampered'")


def test_authenticated_cannot_delete_an_audit_event(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, TENANT_A)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from audit_event")


def test_writer_records_an_event_for_the_callers_own_tenant(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, TENANT_A)
        cur.execute("select record_audit_event('test.event', 'success')")
        row = cur.fetchone()
        assert row is not None and row[0] > 0


def test_writer_refuses_an_event_for_another_tenant(conn: psycopg.Connection) -> None:
    """SECURITY DEFINER gives the function elevated rights; it must not lend them to the caller."""
    with conn.cursor() as cur:
        act_as_member(cur, TENANT_A)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "select record_audit_event('forged.event', 'success', %s::uuid)", (TENANT_B,)
            )


def test_writer_records_a_pre_authentication_event(conn: psycopg.Connection) -> None:
    """A failed sign-in has no tenant and no session, and must still be recorded (FR-006)."""
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', '{}', true)")
        cur.execute(
            "select record_audit_event('auth.failed', 'refused', null, null, %s)",
            ("someone@example.test",),
        )
        row = cur.fetchone()
        assert row is not None and row[0] > 0
