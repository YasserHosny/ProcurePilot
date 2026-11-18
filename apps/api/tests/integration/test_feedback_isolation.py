"""In-app feedback is isolated by the database — spec 025, task T005.

Principle V: tenant isolation lives in Postgres, so these run against a real database with the
real migrations (through 20261118000500) as the real `authenticated` role carrying a JWT claim.
A mock would prove nothing.

Covered here: both tables exist with RLS enabled AND forced; one workspace cannot read, insert,
update or delete another's rows; a member can change no column; own-or-owner visibility; operator
reach and forward-only status; `platform_operator` and `is_platform_operator()` are unreachable
by clients except the function's boolean result.

Set TEST_DATABASE_URL to a database with the migrations applied. Skipped when unset.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


@dataclass
class Member:
    user_id: UUID
    membership_id: UUID
    role: str


@dataclass
class Tenant:
    tenant_id: UUID
    owner: Member
    buyer: Member
    owner_submission_id: UUID
    buyer_submission_id: UUID
    buyer_attachment_id: UUID


def _claims(tenant_id: UUID, member: Member) -> str:
    return json.dumps(
        {
            "sub": str(member.user_id),
            "tenant_id": str(tenant_id),
            "role": "authenticated",
            "member_role": member.role,
        }
    )


def _act_as(cur: psycopg.Cursor, tenant: Tenant, member: Member) -> None:
    cur.execute("reset role")
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)", (_claims(tenant.tenant_id, member),)
    )


def _act_as_postgres(cur: psycopg.Cursor) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', '{}', true)")


def _member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Member:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)", (user_id, f"{label}@example.test")
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Member(user_id, membership_id, role)


def _submission(
    cur: psycopg.Cursor, tenant_id: UUID, member: Member, label: str
) -> tuple[UUID, UUID]:
    submission_id, attachment_id = uuid4(), uuid4()
    cur.execute(
        "insert into feedback_submission "
        "(id,tenant_id,submitter_user_id,submitter_membership_id,submitter_name,submitter_email,"
        "member_role,text_content,page_path,app_version,locale,is_demo,idempotency_key) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,'/home','test','en',false,%s)",
        (
            submission_id,
            tenant_id,
            member.user_id,
            member.membership_id,
            label,
            f"{label}@example.test",
            member.role,
            f"{label} says hello",
            uuid4(),
        ),
    )
    cur.execute(
        "insert into feedback_attachment "
        "(id,tenant_id,submission_id,kind,storage_path,content_type,size_bytes,display_order) "
        "values (%s,%s,%s,'image',%s,'image/png',2048,0)",
        (
            attachment_id,
            tenant_id,
            submission_id,
            f"tenants/{tenant_id}/feedback/{submission_id}/{label}.png",
        ),
    )
    return submission_id, attachment_id


def _tenant(cur: psycopg.Cursor, label: str) -> Tenant:
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
    owner = _member(cur, tenant_id, f"{label}-owner", "owner")
    buyer = _member(cur, tenant_id, f"{label}-buyer", "buyer")
    owner_sub, _ = _submission(cur, tenant_id, owner, f"{label}-owner")
    buyer_sub, buyer_att = _submission(cur, tenant_id, buyer, f"{label}-buyer")
    return Tenant(tenant_id, owner, buyer, owner_sub, buyer_sub, buyer_att)


@pytest.fixture
def world() -> Iterator[tuple[psycopg.Connection, Tenant, Tenant]]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            alpha = _tenant(cur, "alpha")
            beta = _tenant(cur, "beta")
        yield conn, alpha, beta
        conn.rollback()


def _grant_operator(cur: psycopg.Cursor, member: Member, *, revoked: bool = False) -> None:
    _act_as_postgres(cur)
    cur.execute(
        "insert into platform_operator (user_id,email,granted_by,revoked_at) "
        "values (%s,%s,'test', case when %s then now() end)",
        (member.user_id, f"op-{member.user_id}@example.test", revoked),
    )


# --- schema shape -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table", ["feedback_submission", "feedback_attachment", "platform_operator"]
)
def test_rls_is_enabled_and_forced(
    world: tuple[psycopg.Connection, Tenant, Tenant], table: str
) -> None:
    conn, _a, _b = world
    with conn.cursor() as cur:
        cur.execute(
            "select relrowsecurity, relforcerowsecurity from pg_class "
            "where relname = %s and relnamespace = 'public'::regnamespace",
            (table,),
        )
        assert cur.fetchone() == (True, True), f"{table} must ENABLE and FORCE RLS"


# --- cross-workspace isolation ------------------------------------------------------------


def test_workspace_cannot_read_another_workspaces_feedback(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        cur.execute(
            "select id from feedback_submission where id = any(%s)",
            ([beta.owner_submission_id, beta.buyer_submission_id],),
        )
        assert cur.fetchall() == []
        cur.execute("select id from feedback_attachment where id = %s", (beta.buyer_attachment_id,))
        assert cur.fetchall() == []


def test_workspace_cannot_insert_feedback_into_another_workspace(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into feedback_submission "
                "(tenant_id,submitter_user_id,submitter_name,submitter_email,member_role,"
                "text_content,page_path,app_version,locale,is_demo,idempotency_key) "
                "values (%s,%s,'x','x@example.test','owner','hi','/','t','en',false,%s)",
                (beta.tenant_id, alpha.owner.user_id, uuid4()),
            )


def test_workspace_cannot_attach_to_another_workspaces_submission(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "insert into feedback_attachment "
                "(tenant_id,submission_id,kind,storage_path,content_type,size_bytes,"
                "display_order) values (%s,%s,'image',%s,'image/png',10,1)",
                (
                    beta.tenant_id,
                    beta.buyer_submission_id,
                    f"tenants/{beta.tenant_id}/feedback/{beta.buyer_submission_id}/x.png",
                ),
            )


def test_cross_workspace_update_and_delete_change_nothing(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        cur.execute(
            "update feedback_submission set status = 'resolved' where id = %s",
            (beta.buyer_submission_id,),
        )
        assert cur.rowcount == 0
        cur.execute("delete from feedback_submission where id = %s", (beta.buyer_submission_id,))
        assert cur.rowcount == 0
        _act_as_postgres(cur)
        cur.execute(
            "select status::text from feedback_submission where id = %s",
            (beta.buyer_submission_id,),
        )
        assert cur.fetchone() == ("new",)


def test_no_tenant_claim_sees_nothing(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, _a, _b = world
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', '{}', true)")
        cur.execute("select count(*) from feedback_submission")
        assert cur.fetchone() == (0,)


# --- within a workspace -------------------------------------------------------------------


def test_member_sees_only_own_submissions_and_owner_sees_all(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("select id from feedback_submission")
        assert cur.fetchall() == [(alpha.buyer_submission_id,)]
        _act_as(cur, alpha, alpha.owner)
        cur.execute("select id from feedback_submission order by created_at, id")
        assert {r[0] for r in cur.fetchall()} == {
            alpha.owner_submission_id,
            alpha.buyer_submission_id,
        }


@pytest.mark.parametrize("column,value", [("status", "'resolved'"), ("labels", "array['x']")])
def test_member_cannot_change_status_or_labels(
    world: tuple[psycopg.Connection, Tenant, Tenant], column: str, value: str
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.buyer)
        cur.execute(
            f"update feedback_submission set {column} = {value} where id = %s",  # noqa: S608
            (alpha.buyer_submission_id,),
        )
        assert cur.rowcount == 0, "no update policy applies to members"


@pytest.mark.parametrize(
    "column,value",
    [
        ("text_content", "'edited'"),
        ("category", "'bug'"),
        ("tenant_id", "gen_random_uuid()"),
        ("submitter_user_id", "gen_random_uuid()"),
        ("is_demo", "true"),
        ("page_path", "'/other'"),
    ],
)
def test_member_cannot_update_any_other_column(
    world: tuple[psycopg.Connection, Tenant, Tenant], column: str, value: str
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                f"update feedback_submission set {column} = {value} where id = %s",  # noqa: S608
                (alpha.owner_submission_id,),
            )


def test_member_cannot_insert_a_forged_row(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    """Someone else's user id, a non-new status, or labels at insert are all refused."""
    conn, alpha, _b = world
    base = (
        "insert into feedback_submission "
        "(tenant_id,submitter_user_id,submitter_name,submitter_email,member_role,text_content,"
        "page_path,app_version,locale,is_demo,idempotency_key{extra_cols}) "
        "values (%s,%s,'x','x@example.test','buyer','hi','/','t','en',false,%s{extra_vals})"
    )
    cases = [
        (
            base.format(extra_cols="", extra_vals=""),
            (alpha.tenant_id, alpha.owner.user_id, uuid4()),
        ),
        (
            base.format(extra_cols=",status", extra_vals=",'resolved'"),
            (alpha.tenant_id, alpha.buyer.user_id, uuid4()),
        ),
        (
            base.format(extra_cols=",labels", extra_vals=",array['x']"),
            (alpha.tenant_id, alpha.buyer.user_id, uuid4()),
        ),
    ]
    for sql, params in cases:
        with conn.cursor() as cur:
            cur.execute("savepoint s")
            _act_as(cur, alpha, alpha.buyer)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql, params)
            cur.execute("rollback to savepoint s")


def test_member_can_submit_and_withdraw_own_new_submission_only(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.buyer)
        new_id = uuid4()
        cur.execute(
            "insert into feedback_submission "
            "(id,tenant_id,submitter_user_id,submitter_name,submitter_email,member_role,"
            "text_content,page_path,app_version,locale,is_demo,idempotency_key) "
            "values (%s,%s,%s,'x','x@example.test','buyer','hi','/','t','en',false,%s)",
            (new_id, alpha.tenant_id, alpha.buyer.user_id, uuid4()),
        )
        cur.execute("delete from feedback_submission where id = %s", (new_id,))
        assert cur.rowcount == 1
        # Another member's submission in the same workspace: not theirs to withdraw.
        cur.execute("delete from feedback_submission where id = %s", (alpha.owner_submission_id,))
        assert cur.rowcount == 0


def test_member_cannot_withdraw_a_reviewed_submission(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as_postgres(cur)
        cur.execute(
            "update feedback_submission set status = 'reviewed' where id = %s",
            (alpha.buyer_submission_id,),
        )
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("delete from feedback_submission where id = %s", (alpha.buyer_submission_id,))
        assert cur.rowcount == 0


def test_withdrawing_a_submission_removes_its_attachments(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("delete from feedback_submission where id = %s", (alpha.buyer_submission_id,))
        assert cur.rowcount == 1
        _act_as_postgres(cur)
        cur.execute(
            "select count(*) from feedback_attachment where submission_id = %s",
            (alpha.buyer_submission_id,),
        )
        assert cur.fetchone() == (0,)


def test_attachment_rows_have_no_client_update_or_delete(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.buyer)
        for sql in (
            "update feedback_attachment set size_bytes = 1 where id = %s",
            "delete from feedback_attachment where id = %s",
        ):
            cur.execute("savepoint s")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql, (alpha.buyer_attachment_id,))
            cur.execute("rollback to savepoint s")


# --- platform operator ---------------------------------------------------------------------


def test_operator_reads_across_workspaces_and_moves_status_forward_only(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _grant_operator(cur, alpha.buyer)
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("select count(*) from feedback_submission")
        assert cur.fetchone() == (4,)
        cur.execute(
            "select count(*) from feedback_attachment where id = %s", (beta.buyer_attachment_id,)
        )
        assert cur.fetchone() == (1,)

        cur.execute(
            "update feedback_submission set status = 'reviewed', labels = array['bug-confirmed'] "
            "where id = %s",
            (beta.owner_submission_id,),
        )
        assert cur.rowcount == 1
        cur.execute(
            "select status::text, status_changed_by, status_changed_at is not null "
            "from feedback_submission where id = %s",
            (beta.owner_submission_id,),
        )
        assert cur.fetchone() == ("reviewed", alpha.buyer.user_id, True)

        cur.execute("savepoint s")
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "update feedback_submission set status = 'new' where id = %s",
                (beta.owner_submission_id,),
            )
        cur.execute("rollback to savepoint s")

        cur.execute(
            "update feedback_submission set status = 'resolved' where id = %s",
            (beta.owner_submission_id,),
        )
        assert cur.rowcount == 1


def test_only_status_and_labels_can_change_even_for_a_privileged_role(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    """Operators lack the column grant; the trigger is the second wall for roles that have it."""
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _grant_operator(cur, alpha.buyer)
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("savepoint s")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update feedback_submission set text_content = 'rewritten' where id = %s",
                (beta.owner_submission_id,),
            )
        cur.execute("rollback to savepoint s")

        _act_as_postgres(cur)  # superuser skips grants and RLS, but not triggers
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "update feedback_submission set text_content = 'rewritten' where id = %s",
                (beta.owner_submission_id,),
            )


def test_status_changed_columns_cannot_be_forged(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, beta = world
    with conn.cursor() as cur:
        _grant_operator(cur, alpha.buyer)
        _act_as(cur, alpha, alpha.buyer)
        cur.execute(
            "update feedback_submission set status_changed_by = gen_random_uuid(), "
            "status_changed_at = '2000-01-01' where id = %s",
            (beta.owner_submission_id,),
        )
        cur.execute(
            "select status_changed_by, status_changed_at from feedback_submission where id = %s",
            (beta.owner_submission_id,),
        )
        assert cur.fetchone() == (None, None), "no status change, so the trigger keeps them null"


def test_a_revoked_operator_has_no_operator_access(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _grant_operator(cur, alpha.buyer, revoked=True)
        _act_as(cur, alpha, alpha.buyer)
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (False,)
        cur.execute("select count(*) from feedback_submission")
        assert cur.fetchone() == (1,)


# --- platform_operator is unreachable to clients ------------------------------------------


def test_is_platform_operator_is_false_for_members_and_true_for_operators(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (False,)
        _grant_operator(cur, alpha.owner)
        _act_as(cur, alpha, alpha.owner)
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (True,)


def test_is_platform_operator_survives_empty_claims(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, _a, _b = world
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', '', true)")
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (False,)


@pytest.mark.parametrize(
    "sql",
    [
        "select * from platform_operator",
        "insert into platform_operator (user_id,email,granted_by) "
        "values (gen_random_uuid(),'x@example.test','x')",
        "update platform_operator set digest_opt_in = true",
        "delete from platform_operator",
    ],
)
def test_platform_operator_table_is_unreachable_by_authenticated(
    world: tuple[psycopg.Connection, Tenant, Tenant], sql: str
) -> None:
    conn, alpha, _b = world
    with conn.cursor() as cur:
        _act_as(cur, alpha, alpha.owner)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(sql)


def test_platform_operator_table_and_function_are_unreachable_by_anon(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, _a, _b = world
    with conn.cursor() as cur:
        for sql in ("select * from platform_operator", "select is_platform_operator()"):
            cur.execute("reset role")
            cur.execute("savepoint s")
            cur.execute("set local role anon")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql)
            cur.execute("rollback to savepoint s")


def test_feedback_tables_are_unreachable_by_anon(
    world: tuple[psycopg.Connection, Tenant, Tenant],
) -> None:
    conn, _a, _b = world
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select count(*) from feedback_submission")
