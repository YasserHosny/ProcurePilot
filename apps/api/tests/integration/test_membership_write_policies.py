"""membership writes through the database match the API's rules (20261018000010).

A member may change only their own preferred_locale; only an owner (by their live membership row,
not the JWT claim) may change a member's role, status or is_active_workspace; nobody inserts or
deletes membership rows as `authenticated`. Reads stay workspace-wide.
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


def add_member(cur: psycopg.Cursor, tenant_id: UUID, role: str) -> tuple[UUID, UUID]:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, f"{user_id}@t"))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{user_id}@t", role),
    )
    return membership_id, user_id


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


type Workspace = tuple[psycopg.Cursor, UUID, dict[str, tuple[UUID, UUID]]]


@pytest.fixture
def workspace(
    conn: psycopg.Connection,
) -> tuple[psycopg.Cursor, UUID, dict[str, tuple[UUID, UUID]]]:
    cur = conn.cursor()
    tenant_id = make_tenant(cur)
    members = {
        "owner": add_member(cur, tenant_id, "owner"),
        "viewer": add_member(cur, tenant_id, "viewer"),
        "buyer": add_member(cur, tenant_id, "buyer"),
    }
    return cur, tenant_id, members


def _role_of(cur: psycopg.Cursor, membership_id: UUID) -> str:
    cur.execute("reset role")
    cur.execute("select role::text from membership where id = %s", (membership_id,))
    return str(cur.fetchone()[0])


# --- a non-owner cannot escalate ---------------------------------------------------------------


@pytest.mark.parametrize("claim_role", ["viewer", "owner"])
def test_a_viewer_cannot_change_their_own_role_even_with_an_owner_claim(
    workspace: Workspace, claim_role: str
) -> None:
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, claim_role)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("update membership set role = 'owner' where id = %s", (viewer_id,))
    cur.connection.rollback()


def test_a_viewer_cannot_change_their_own_status(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "viewer")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("update membership set status = 'removed' where id = %s", (viewer_id,))


def test_a_buyer_cannot_change_another_members_row(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    viewer_id, _ = members["viewer"]
    _, buyer_user = members["buyer"]
    act_as(cur, tenant_id, buyer_user, "owner")
    cur.execute("update membership set preferred_locale = 'ar' where id = %s", (viewer_id,))
    assert cur.rowcount == 0
    # Another member's row is outside the UPDATE policy for a non-owner: nothing matches.
    cur.execute("update membership set role = 'buyer' where id = %s", (viewer_id,))
    assert cur.rowcount == 0
    assert _role_of(cur, viewer_id) == "viewer"


def test_authenticated_cannot_insert_or_delete_membership(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "owner")
    cur.execute("savepoint before_insert")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "insert into membership (tenant_id,user_id,email,role) values (%s,%s,'x@t','owner')",
            (tenant_id, viewer_user),
        )
    cur.execute("rollback to savepoint before_insert")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("delete from membership where id = %s", (viewer_id,))


@pytest.mark.parametrize(
    ("column", "value"), [("tenant_id", str(uuid4())), ("email", "'x@t'"), ("user_id", None)]
)
def test_identity_columns_are_not_updatable(
    workspace: Workspace, column: str, value: str | None
) -> None:
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "viewer")
    new_value = value if value is not None else f"'{uuid4()}'"
    if column == "tenant_id":
        new_value = f"'{value}'"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(f"update membership set {column} = {new_value} where id = %s", (viewer_id,))


# --- what the API does keeps working -----------------------------------------------------------


def test_a_member_can_change_their_own_preferred_locale(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "viewer")
    cur.execute("update membership set preferred_locale = 'ar' where id = %s", (viewer_id,))
    assert cur.rowcount == 1


def test_an_owner_can_change_a_members_role_and_remove_a_member(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    viewer_id, _ = members["viewer"]
    buyer_id, _ = members["buyer"]
    _, owner_user = members["owner"]
    act_as(cur, tenant_id, owner_user, "owner")
    cur.execute("update membership set role = 'buyer' where id = %s", (viewer_id,))
    assert cur.rowcount == 1
    cur.execute(
        "update membership set status = 'removed', is_active_workspace = false where id = %s",
        (buyer_id,),
    )
    assert cur.rowcount == 1
    assert _role_of(cur, viewer_id) == "buyer"


def test_a_demoted_owner_with_a_stale_owner_claim_cannot_change_roles(
    workspace: Workspace,
) -> None:
    """buyer's token says owner (issued before a demotion); their live row says buyer."""
    cur, tenant_id, members = workspace
    viewer_id, _ = members["viewer"]
    buyer_id, buyer_user = members["buyer"]
    act_as(cur, tenant_id, buyer_user, "owner")
    cur.execute("update membership set role = 'buyer' where id = %s", (viewer_id,))
    assert cur.rowcount == 0
    cur.execute("savepoint self_promotion")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("update membership set role = 'owner' where id = %s", (buyer_id,))
    cur.execute("rollback to savepoint self_promotion")
    assert _role_of(cur, viewer_id) == "viewer"
    assert _role_of(cur, buyer_id) == "buyer"


def test_a_non_owner_cannot_change_their_own_active_workspace_flag(workspace: Workspace) -> None:
    """Workspace switching goes through set_active_workspace (SECURITY DEFINER) instead."""
    cur, tenant_id, members = workspace
    viewer_id, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "viewer")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("update membership set is_active_workspace = false where id = %s", (viewer_id,))


def test_members_still_read_the_whole_workspace(workspace: Workspace) -> None:
    cur, tenant_id, members = workspace
    _, viewer_user = members["viewer"]
    act_as(cur, tenant_id, viewer_user, "viewer")
    cur.execute("select count(*) from membership")
    assert cur.fetchone()[0] == 3
