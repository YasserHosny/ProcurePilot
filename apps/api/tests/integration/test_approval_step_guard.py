"""A client session can only decide the step it is assigned (or an owner's), once (PPS-166, P-172).

`approval_step_tenant_isolation` keeps a session inside its tenant but says nothing about *which*
step it writes or how, so a member talking to the database directly could decide a step assigned to
someone else, forge `decided_by_membership_id`, re-open a decided step, rewrite who it is assigned
to, or delete it. The `approval_step_guard_client_write` trigger (20261105000100) allows a client
role (`authenticated`, `anon`) exactly what the API does under it -- insert a pending step at
submission, decide a pending step as its assignee or an owner, and let an owner hand a pending step
to an owner when its approver leaves -- and leaves everything else to server-side roles.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    connection,
    make_workspace,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the migrations applied",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


def _member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Workspace:
    user_id, membership_id = uuid4(), uuid4()
    email = f"{label}-{user_id.hex[:8]}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, email, role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


class Fixture:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        with conn.cursor() as cur:
            self.owner = make_workspace(cur, "stepguard", role="owner")
            self.owner2 = _member(cur, self.owner.tenant_id, "owner2", "owner")
            self.approver = _member(cur, self.owner.tenant_id, "approver", "approver")
            self.other = _member(cur, self.owner.tenant_id, "other", "approver")
            self.requester = _member(cur, self.owner.tenant_id, "requester", "buyer")
            self.branch_id = uuid4()
            cur.execute(
                "insert into branch (id,tenant_id,name,region) values (%s,%s,'Main','GB')",
                (self.branch_id, self.owner.tenant_id),
            )

    def request(self, status: str = "submitted") -> UUID:
        request_id = uuid4()
        with self.conn.cursor() as cur:
            cur.execute("reset role")
            cur.execute(
                "insert into purchase_request "
                "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status) "
                "values (%s,%s,%s,%s,current_date + interval '7 days',%s)",
                (
                    request_id,
                    self.owner.tenant_id,
                    self.branch_id,
                    self.requester.membership_id,
                    status,
                ),
            )
        return request_id

    def step(self, *, status: str = "pending", assigned: Workspace | None = None) -> UUID:
        """A step created as the table owner (the guard only restricts client roles)."""
        request_id = self.request()
        step_id = uuid4()
        assigned = assigned or self.approver
        with self.conn.cursor() as cur:
            cur.execute("reset role")
            if status == "pending":
                cur.execute(
                    "insert into approval_step "
                    "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
                    "values (%s,%s,%s,%s,'threshold_match','pending')",
                    (step_id, self.owner.tenant_id, request_id, assigned.membership_id),
                )
            else:
                cur.execute(
                    "insert into approval_step "
                    "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status,"
                    "decided_by_membership_id,decided_at) "
                    "values (%s,%s,%s,%s,'threshold_match',%s,%s,now())",
                    (
                        step_id,
                        self.owner.tenant_id,
                        request_id,
                        assigned.membership_id,
                        status,
                        assigned.membership_id,
                    ),
                )
        return step_id

    def act_as(self, who: Workspace) -> psycopg.Cursor:
        cur = self.conn.cursor()
        cur.execute("savepoint before_attempt")
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', %s, true)", (who.claims(),))
        return cur

    def row(self, step_id: UUID) -> tuple:
        with self.conn.cursor() as cur:
            cur.execute("reset role")
            cur.execute(
                "select status, decided_by_membership_id, assigned_membership_id, source, comment "
                "from approval_step where id = %s",
                (step_id,),
            )
            return cur.fetchone()


@pytest.fixture
def fx(conn: psycopg.Connection) -> Fixture:
    return Fixture(conn)


def _decide(
    cur: psycopg.Cursor, step_id: UUID, status: str, by: UUID, comment: str | None = None
) -> None:
    cur.execute(
        "update approval_step set status=%s, comment=%s, decided_by_membership_id=%s, "
        "decided_at=now() where id=%s",
        (status, comment, by, step_id),
    )


def _denied(conn: psycopg.Connection) -> None:
    """Undo the refused statement and the role switch, keeping the fixture rows."""
    conn.execute("rollback to savepoint before_attempt")


# ---- the paths the API uses keep working -------------------------------------------------


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_the_assigned_approver_can_decide(fx: Fixture, decision: str) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.approver)
    _decide(cur, step_id, decision, fx.approver.membership_id, "ok")
    assert fx.row(step_id)[:2] == (decision, fx.approver.membership_id)


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_an_owner_can_decide_a_step_assigned_to_someone_else(fx: Fixture, decision: str) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.owner)
    _decide(cur, step_id, decision, fx.owner.membership_id)
    assert fx.row(step_id)[:2] == (decision, fx.owner.membership_id)


def test_a_requester_can_insert_a_pending_step_for_submission(fx: Fixture) -> None:
    request_id = fx.request()
    cur = fx.act_as(fx.requester)
    step_id = uuid4()
    cur.execute(
        "insert into approval_step "
        "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
        "values (%s,%s,%s,%s,'threshold_match','pending')",
        (step_id, fx.owner.tenant_id, request_id, fx.approver.membership_id),
    )
    assert fx.row(step_id)[0] == "pending"


def test_an_owner_can_hand_a_pending_step_to_an_owner_when_its_approver_leaves(
    fx: Fixture,
) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.owner)
    cur.execute(
        "update approval_step set assigned_membership_id=%s, source='owner_fallback' where id=%s",
        (fx.owner2.membership_id, step_id),
    )
    row = fx.row(step_id)
    assert (row[0], row[2], row[3]) == ("pending", fx.owner2.membership_id, "owner_fallback")


# ---- everything else is refused ----------------------------------------------------------


def test_a_member_who_is_not_the_assignee_cannot_decide(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.other)
    # Either refused outright, or the step is not even visible to this member (no row updated).
    try:
        _decide(cur, step_id, "approved", fx.other.membership_id)
    except psycopg.errors.InsufficientPrivilege:
        _denied(fx.conn)
    assert fx.row(step_id)[0] == "pending"


def test_the_requester_cannot_decide_their_own_request(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.requester)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _decide(cur, step_id, "approved", fx.requester.membership_id)
    _denied(fx.conn)


def test_a_decision_cannot_name_another_member_as_the_decider(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.approver)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _decide(cur, step_id, "approved", fx.owner.membership_id)
    _denied(fx.conn)


@pytest.mark.parametrize("stored", ["approved", "rejected"])
@pytest.mark.parametrize("target", ["pending", "approved", "rejected"])
def test_a_decided_step_cannot_be_changed(fx: Fixture, stored: str, target: str) -> None:
    step_id = fx.step(status=stored)
    cur = fx.act_as(fx.owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        if target == "pending":
            cur.execute(
                "update approval_step set status='pending', decided_by_membership_id=null, "
                "decided_at=null where id=%s",
                (step_id,),
            )
        else:
            _decide(cur, step_id, target, fx.owner.membership_id)
    _denied(fx.conn)
    assert fx.row(step_id)[0] == stored


def test_a_pending_step_cannot_be_edited_without_a_decision(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.approver)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("update approval_step set comment='x' where id=%s", (step_id,))
    _denied(fx.conn)


def test_an_approver_cannot_reassign_a_step(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.approver)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "update approval_step set assigned_membership_id=%s where id=%s",
            (fx.other.membership_id, step_id),
        )
    _denied(fx.conn)


def test_an_owner_cannot_hand_a_step_to_a_non_owner(fx: Fixture) -> None:
    step_id = fx.step()
    cur = fx.act_as(fx.owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "update approval_step set assigned_membership_id=%s, source='owner_fallback' "
            "where id=%s",
            (fx.other.membership_id, step_id),
        )
    _denied(fx.conn)


def test_a_step_cannot_be_moved_to_another_request(fx: Fixture) -> None:
    step_id = fx.step()
    other_request = fx.request()
    cur = fx.act_as(fx.owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "update approval_step set purchase_request_id=%s where id=%s",
            (other_request, step_id),
        )
    _denied(fx.conn)


@pytest.mark.parametrize("who", ["owner", "approver", "requester"])
def test_no_client_session_can_delete_a_step(fx: Fixture, who: str) -> None:
    step_id = fx.step()
    cur = fx.act_as(getattr(fx, who))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("delete from approval_step where id=%s", (step_id,))
    _denied(fx.conn)


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_a_step_cannot_be_inserted_already_decided(fx: Fixture, status: str) -> None:
    request_id = fx.request()
    cur = fx.act_as(fx.owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "insert into approval_step "
            "(tenant_id,purchase_request_id,assigned_membership_id,source,status,"
            "decided_by_membership_id,decided_at) "
            "values (%s,%s,%s,'threshold_match',%s,%s,now())",
            (
                fx.owner.tenant_id,
                request_id,
                fx.approver.membership_id,
                status,
                fx.owner.membership_id,
            ),
        )
    _denied(fx.conn)


# ---- server-side roles are not restricted ------------------------------------------------


def test_the_table_owner_is_not_restricted(fx: Fixture) -> None:
    step_id = fx.step(status="approved")
    with fx.conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute(
            "update approval_step set status='pending', decided_by_membership_id=null, "
            "decided_at=null where id=%s",
            (step_id,),
        )
        cur.execute("delete from approval_step where id=%s", (step_id,))
