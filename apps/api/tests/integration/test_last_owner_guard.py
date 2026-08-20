"""A workspace must always retain at least one active owner — task T052 (FR-012).

The rule is a cardinality MINIMUM: it concerns how many *other* rows survive a change, which no
unique or check constraint can express. It therefore lives in a trigger, and these tests exercise
it through every path that could otherwise strand a workspace with nobody able to administer it:
demotion, removal, and the self-service versions of both.

A workspace with no owner cannot invite, cannot change roles, and cannot recover without support
intervention — so this is a data-integrity rule, not a convenience.
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


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def make_tenant(cur: psycopg.Cursor) -> UUID:
    tenant_id, invitation_id = uuid4(), uuid4()
    cur.execute(
        "insert into supported_region (code,label_en,label_ar) values ('GB','UK','ب') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_currency (code,label_en,label_ar) values ('GBP','P','ج') "
        "on conflict do nothing"
    )
    cur.execute(
        "insert into supported_tax_model (code,label_en,label_ar,region_code) "
        "values ('uk_vat','V','ض','GB') on conflict do nothing"
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,'p@t',%s, now() + interval '7 days')",
        (invitation_id, f"h-{invitation_id}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,'T',%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"t-{tenant_id.hex[:10]}", invitation_id),
    )
    return tenant_id


def add_member(cur: psycopg.Cursor, tenant_id: UUID, role: str) -> UUID:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, f"{user_id}@t"))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role) values (%s,%s,%s,%s,%s)",
        (membership_id, tenant_id, user_id, f"{user_id}@t", role),
    )
    return membership_id


# --- the guard holds -------------------------------------------------------


def test_the_only_owner_cannot_be_demoted(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        owner = add_member(cur, tenant, "owner")
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("update membership set role = 'viewer' where id = %s", (owner,))


def test_the_only_owner_cannot_be_deleted(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        owner = add_member(cur, tenant, "owner")
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("delete from membership where id = %s", (owner,))


def test_the_only_owner_cannot_be_deactivated(conn: psycopg.Connection) -> None:
    """Removal is a status change, so the guard must cover status too, not only role."""
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        owner = add_member(cur, tenant, "owner")
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("update membership set status = 'removed' where id = %s", (owner,))


def test_the_last_active_owner_cannot_be_demoted_when_another_owner_is_removed(
    conn: psycopg.Connection,
) -> None:
    """A *removed* owner does not count. Two owners, one already gone, is one owner."""
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        keeper = add_member(cur, tenant, "owner")
        gone = add_member(cur, tenant, "owner")
        cur.execute("update membership set status = 'removed' where id = %s", (gone,))
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("update membership set role = 'viewer' where id = %s", (keeper,))


def test_a_workspace_cannot_be_emptied_of_owners_one_at_a_time(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        first = add_member(cur, tenant, "owner")
        second = add_member(cur, tenant, "owner")
        cur.execute("update membership set role = 'viewer' where id = %s", (first,))
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("update membership set role = 'viewer' where id = %s", (second,))


# --- the guard does not over-reach ------------------------------------------


def test_one_of_two_owners_can_be_demoted(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        add_member(cur, tenant, "owner")
        second = add_member(cur, tenant, "owner")
        cur.execute("update membership set role = 'viewer' where id = %s", (second,))
        assert cur.rowcount == 1


def test_a_non_owner_can_always_be_removed(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        add_member(cur, tenant, "owner")
        buyer = add_member(cur, tenant, "buyer")
        cur.execute("update membership set status = 'removed' where id = %s", (buyer,))
        assert cur.rowcount == 1


def test_promoting_a_member_to_owner_is_unaffected(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        tenant = make_tenant(cur)
        add_member(cur, tenant, "owner")
        viewer = add_member(cur, tenant, "viewer")
        cur.execute("update membership set role = 'owner' where id = %s", (viewer,))
        assert cur.rowcount == 1


def test_another_workspaces_sole_owner_is_irrelevant(conn: psycopg.Connection) -> None:
    """The rule is per workspace. One tenant's owner count must not license changes in another."""
    with conn.cursor() as cur:
        tenant_a, tenant_b = make_tenant(cur), make_tenant(cur)
        add_member(cur, tenant_a, "owner")
        add_member(cur, tenant_a, "owner")
        sole_owner_of_b = add_member(cur, tenant_b, "owner")
        with pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute("update membership set role = 'viewer' where id = %s", (sole_owner_of_b,))
