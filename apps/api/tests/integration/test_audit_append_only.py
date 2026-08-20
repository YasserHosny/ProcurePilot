"""audit_event is append-only, and the audit writer cannot forge tenancy — task T035.

These run against a real Postgres with the migrations applied. The guarantees under test live in
the database, so testing them against a mock would prove nothing at all.

Set TEST_DATABASE_URL to a database with migrations 0001-0007 applied. Skipped when unset, so a
developer without a database can still run the rest of the suite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

def make_tenant(cur: psycopg.Cursor, label: str) -> UUID:
    """Create a self-contained tenant.

    These tests used to reference fixed uuids seeded elsewhere, which made them pass or fail
    according to whatever happened to be in the database. Each test now builds what it needs.
    """
    tenant_id, invitation_id = uuid4(), uuid4()
    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','Pound','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"{label}@example.test", f"hash-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    return tenant_id


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def act_as_member(cur: psycopg.Cursor, tenant_id: UUID | str) -> None:
    """Become the `authenticated` role carrying a tenant claim, as a real request would."""
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (f'{{"tenant_id":"{tenant_id}","role":"authenticated","member_role":"owner"}}',),
    )


def test_authenticated_cannot_update_an_audit_event(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, make_tenant(cur, "upd"))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("update audit_event set action = 'tampered'")


def test_authenticated_cannot_delete_an_audit_event(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, make_tenant(cur, "del"))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("delete from audit_event")


def test_writer_records_an_event_for_the_callers_own_tenant(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        act_as_member(cur, make_tenant(cur, "own"))
        cur.execute("select record_audit_event('test.event', 'success')")
        row = cur.fetchone()
        assert row is not None and row[0] > 0


def test_writer_refuses_an_event_for_another_tenant(conn: psycopg.Connection) -> None:
    """SECURITY DEFINER gives the function elevated rights; it must not lend them to the caller."""
    with conn.cursor() as cur:
        mine = make_tenant(cur, "mine")
        theirs = make_tenant(cur, "theirs")
        act_as_member(cur, mine)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "select record_audit_event('forged.event', 'success', %s::uuid)", (theirs,)
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
