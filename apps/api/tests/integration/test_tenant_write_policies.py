"""tenant writes through the database match the API's rules (20261018000012).

Only an owner (by their live membership row, not the JWT claim) may change the workspace's name,
language, reporting timezone or currency; nobody inserts or deletes tenant rows, or changes the
workspace's identity columns, as `authenticated`. Every member still reads their own workspace.
"""

from __future__ import annotations

import json
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
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
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
    user_id = uuid4()
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, f"{user_id}@t"))
    cur.execute(
        "insert into membership (tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,true)",
        (tenant_id, user_id, f"{user_id}@t", role),
    )
    return user_id


def act_as(cur: psycopg.Cursor, tenant_id: UUID, user_id: UUID, claim_role: str) -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {
                    "sub": str(user_id),
                    "tenant_id": str(tenant_id),
                    "role": "authenticated",
                    "member_role": claim_role,
                }
            ),
        ),
    )


type Workspace = tuple[psycopg.Cursor, UUID, dict[str, UUID]]


@pytest.fixture
def workspace(conn: psycopg.Connection) -> Workspace:
    cur = conn.cursor()
    tenant_id = make_tenant(cur)
    users = {role: add_member(cur, tenant_id, role) for role in ("owner", "buyer", "viewer")}
    return cur, tenant_id, users


def _name_of(cur: psycopg.Cursor, tenant_id: UUID) -> str:
    cur.execute("reset role")
    cur.execute("select name from tenant where id = %s", (tenant_id,))
    return str(cur.fetchone()[0])


# --- a non-owner cannot change the workspace ---------------------------------------------------


@pytest.mark.parametrize("role", ["buyer", "viewer"])
@pytest.mark.parametrize(
    "assignment", ["name = 'X'", "default_locale = 'ar'", "reporting_timezone = 'Africa/Cairo'"]
)
def test_a_non_owner_cannot_change_the_workspace_even_with_an_owner_claim(
    workspace: Workspace, role: str, assignment: str
) -> None:
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users[role], "owner")
    cur.execute(f"update tenant set {assignment} where id = %s", (tenant_id,))
    assert cur.rowcount == 0
    assert _name_of(cur, tenant_id) == "T"


@pytest.mark.parametrize("role", ["owner", "viewer"])
def test_nobody_inserts_or_deletes_a_tenant_as_authenticated(
    workspace: Workspace, role: str
) -> None:
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users[role], role)
    cur.execute("savepoint before_delete")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("delete from tenant where id = %s", (tenant_id,))
    cur.execute("rollback to savepoint before_delete")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "insert into tenant (name,slug,region,currency,tax_model) "
            "values ('N','n-slug','GB','GBP','uk_vat')"
        )


@pytest.mark.parametrize(
    "assignment",
    ["slug = 'taken'", "region = 'GB'", "tax_model = 'uk_vat'", "platform_invitation_id = null"],
)
def test_an_owner_cannot_change_identity_columns(workspace: Workspace, assignment: str) -> None:
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users["owner"], "owner")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(f"update tenant set {assignment} where id = %s", (tenant_id,))


def test_an_owner_cannot_touch_another_workspace(workspace: Workspace) -> None:
    cur, tenant_id, users = workspace
    other_tenant = make_tenant(cur)
    act_as(cur, tenant_id, users["owner"], "owner")
    cur.execute("update tenant set name = 'X' where id = %s", (other_tenant,))
    assert cur.rowcount == 0
    assert _name_of(cur, other_tenant) == "T"


# --- what the API does keeps working -----------------------------------------------------------


def test_an_owner_can_change_name_language_timezone_and_currency(workspace: Workspace) -> None:
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users["owner"], "owner")
    cur.execute(
        "update tenant set name = 'Renamed', default_locale = 'ar', "
        "reporting_timezone = 'Africa/Cairo', currency = 'GBP' where id = %s",
        (tenant_id,),
    )
    assert cur.rowcount == 1
    assert _name_of(cur, tenant_id) == "Renamed"


def test_a_demoted_owner_with_a_stale_owner_claim_cannot_change_the_workspace(
    workspace: Workspace,
) -> None:
    """buyer's token says owner (issued before a demotion); their live row says buyer."""
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users["buyer"], "owner")
    cur.execute("update tenant set name = 'X' where id = %s", (tenant_id,))
    assert cur.rowcount == 0


@pytest.mark.parametrize("role", ["owner", "buyer", "viewer"])
def test_every_member_still_reads_their_workspace(workspace: Workspace, role: str) -> None:
    cur, tenant_id, users = workspace
    act_as(cur, tenant_id, users[role], role)
    cur.execute("select id from tenant")
    assert [row[0] for row in cur.fetchall()] == [tenant_id]
