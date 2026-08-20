"""Cross-workspace isolation — task T036. THE test this chunk exists to make possible.

Constitution Principle V: isolation is enforced by the database, so that a forgotten
`where tenant_id = ...` in application code cannot leak another business's commercial data.
Testing that against a mock would prove nothing — these run against a real Postgres with the
real migrations, as the real `authenticated` role, carrying a real JWT claim.

FR-030 requires this to run on every proposed change. It is wired into CI as its own named check
so that its failure is never mistaken for an unrelated test failure.

Set TEST_DATABASE_URL to a database with migrations 0001-0007 applied.
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


class Workspace:
    """One tenant, its owner, and a marker row only that tenant should ever see."""

    def __init__(self, tenant_id: UUID, user_id: UUID, membership_id: UUID, name: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.membership_id = membership_id
        self.name = name

    def claims(self) -> str:
        return (
            f'{{"sub":"{self.user_id}","tenant_id":"{self.tenant_id}",'
            f'"role":"authenticated","member_role":"owner"}}'
        )


def make_workspace(cur: psycopg.Cursor, label: str) -> Workspace:
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()

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
        "insert into auth.users (id,email) values (%s,%s)", (user_id, f"{label}@example.test")
    )
    cur.execute(
        "insert into platform_invitation (id,email,token_hash,expires_at) "
        "values (%s,%s,%s, now() + interval '7 days')",
        (invitation_id, f"{label}@example.test", f"hash-{label}"),
    )
    cur.execute(
        "insert into tenant (id,name,slug,region,currency,tax_model,platform_invitation_id) "
        "values (%s,%s,%s,'GB','GBP','uk_vat',%s)",
        (tenant_id, f"{label} Ltd", f"{label}-{tenant_id.hex[:8]}", invitation_id),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,'owner',true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test"),
    )
    # The marker: a private commercial fact belonging to exactly one workspace.
    cur.execute(
        "insert into audit_event (tenant_id,action,outcome,target) values (%s,%s,'success',%s)",
        (tenant_id, f"{label}.secret", f'{{"secret":"{label}-confidential"}}'),
    )
    return Workspace(tenant_id, user_id, membership_id, f"{label} Ltd")


@pytest.fixture
def workspaces() -> Iterator[tuple[psycopg.Connection, Workspace, Workspace]]:
    """Two unrelated businesses on one database — the situation isolation must survive."""
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = make_workspace(cur, "alpha")
            beta = make_workspace(cur, "beta")
        yield conn, alpha, beta
        conn.rollback()


def act_as(cur: psycopg.Cursor, workspace: Workspace) -> None:
    """Become a member of `workspace`, exactly as a real request arrives."""
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (workspace.claims(),))


# --- reads ------------------------------------------------------------------


def test_a_member_sees_only_their_own_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from tenant")
        rows = cur.fetchall()
    assert [r[0] for r in rows] == [alpha.tenant_id]


def test_fetching_another_workspace_by_id_looks_like_it_does_not_exist(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """FR-005: never reveal that a record exists but is forbidden."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select id from tenant where id = %s", (beta.tenant_id,))
        assert cur.fetchall() == []


def test_another_workspaces_members_are_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from membership where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_another_workspaces_audit_history_is_invisible(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select action from audit_event")
        actions = {r[0] for r in cur.fetchall()}
    assert "beta.secret" not in actions
    assert "alpha.secret" in actions


def test_a_member_cannot_enumerate_other_workspaces(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """Counting must not leak existence either."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- writes -----------------------------------------------------------------


def test_a_member_cannot_write_into_another_workspace(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """WITH CHECK. A USING-only policy would allow this write-then-cannot-read corruption."""
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into member_invitation "
                "(tenant_id,email,role,token_hash,invited_by,expires_at) "
                "values (%s,'intruder@evil.test','owner','h',%s, now() + interval '7 days')",
                (beta.tenant_id, alpha.membership_id),
            )


def test_a_cross_workspace_update_changes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute(
            "update membership set role = 'viewer' where tenant_id = %s", (beta.tenant_id,)
        )
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute(
            "select role from membership where tenant_id = %s", (beta.tenant_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == "owner"


def test_a_cross_workspace_delete_removes_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, alpha, beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        cur.execute("delete from membership where tenant_id = %s", (beta.tenant_id,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from membership where tenant_id = %s", (beta.tenant_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1


# --- absent or forged claims ------------------------------------------------


def test_no_tenant_claim_sees_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """A request that resolves to no workspace must be served nothing, not everything."""
    conn, _alpha, _beta = workspaces
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', '{}', true)")
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_a_malformed_tenant_claim_sees_nothing(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    conn, _alpha, _beta = workspaces
    with conn.cursor() as cur:
        cur.execute("set local role authenticated")
        cur.execute(
            "select set_config('request.jwt.claims', '{\"tenant_id\":\"\"}', true)"
        )
        cur.execute("select count(*) from tenant")
        row = cur.fetchone()
    assert row is not None and row[0] == 0


def test_platform_invitations_are_unreadable_by_members(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """They gate entry to the pilot; a member must not be able to mint or read one."""
    conn, alpha, _beta = workspaces
    with conn.cursor() as cur:
        act_as(cur, alpha)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select count(*) from platform_invitation")


# --- the guarantee itself ---------------------------------------------------


def test_rls_is_enabled_and_forced_on_every_tenant_scoped_table(
    workspaces: tuple[psycopg.Connection, Workspace, Workspace],
) -> None:
    """ENABLE without FORCE exempts the table owner, and migrations run as the owner.

    Without FORCE, every test above could pass while production leaked.
    """
    conn, _alpha, _beta = workspaces
    expected = {"tenant", "membership", "member_invitation", "audit_event", "platform_invitation"}
    with conn.cursor() as cur:
        cur.execute(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class "
            "where relname = any(%s)",
            (list(expected),),
        )
        rows = cur.fetchall()
    assert {r[0] for r in rows} == expected
    for name, enabled, forced in rows:
        assert enabled, f"row level security is not ENABLED on {name}"
        assert forced, f"row level security is not FORCED on {name}"
