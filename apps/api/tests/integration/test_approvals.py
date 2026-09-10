"""Approval-decision integration tests — task T023 (008-requests-approvals, US2).

Proves at the database level:

- the `approval_step` decision-fields-paired check constraint (T003) — a step is `pending`
  if and only if `decided_by_membership_id` and `decided_at` are both null, directly encoding
  FR-006 ("no request becomes approved without a recorded human decision") in the schema;
- `approval_step_one_per_request` — one resolved step per request in this release;
- an approve / reject moves the step and the request together and populates the decision pair;
- the `approval_step_scoped_visibility` RESTRICTIVE policy — the assignee sees their own step,
  the requester sees the step on their own request, an owner sees every step, and any other
  member sees nothing (FR-007's refusal, expressed as invisibility, not a distinguishable
  "forbidden"); a decided step drops out of the pending queue's `status = 'pending'` filter.

The service-layer RBAC guard ("only the assignee or an owner may call approve/reject") and the
HTTP envelopes are covered by test_approvals_contract.py and, once a service-level harness
exists, an API round-trip; here we lock the database guarantees those depend on.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the R2.1 migrations",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def _make_member(
    cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str
) -> Workspace:
    """A second/third membership in an already-created tenant — elevated-role inserts happen
    before any act_as, same as make_workspace's own rows."""
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}@example.test"),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def _make_branch(cur: psycopg.Cursor, ws: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Branch','GB')",
        (branch_id, ws.tenant_id),
    )
    return branch_id


def _make_submitted_request(
    cur: psycopg.Cursor, requester: Workspace, branch_id: UUID
) -> UUID:
    request_id = uuid4()
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status,"
        " submitted_at) "
        "values (%s,%s,%s,%s, current_date + interval '7 days', 'submitted', now())",
        (request_id, requester.tenant_id, branch_id, requester.membership_id),
    )
    return request_id


def _make_pending_step(
    cur: psycopg.Cursor,
    tenant_id: UUID,
    request_id: UUID,
    assignee_membership_id: UUID,
    *,
    source: str = "threshold_match",
) -> UUID:
    step_id = uuid4()
    cur.execute(
        "insert into approval_step "
        "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
        "values (%s,%s,%s,%s,%s,'pending')",
        (step_id, tenant_id, request_id, assignee_membership_id, source),
    )
    return step_id


# ── FR-006: the decision-fields-paired check constraint ───────────────


def test_a_step_cannot_be_decided_without_recording_who_and_when(conn: object) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-c1")
        approver = _make_member(cur, owner.tenant_id, "appr-c1-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        step_id = _make_pending_step(
            cur, owner.tenant_id, request_id, approver.membership_id
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "update approval_step set status = 'approved' where id = %s",
                (step_id,),
            )


def test_a_pending_step_cannot_carry_a_decider_or_a_decided_at(conn: object) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-c2")
        approver = _make_member(cur, owner.tenant_id, "appr-c2-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        step_id = _make_pending_step(
            cur, owner.tenant_id, request_id, approver.membership_id
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "update approval_step set decided_at = now() where id = %s",
                (step_id,),
            )


def test_a_full_decision_pair_satisfies_the_constraint(conn: object) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-c3")
        approver = _make_member(cur, owner.tenant_id, "appr-c3-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        step_id = _make_pending_step(
            cur, owner.tenant_id, request_id, approver.membership_id
        )

        cur.execute(
            "update approval_step set status = 'approved', "
            "decided_by_membership_id = %s, decided_at = now() where id = %s",
            (approver.membership_id, step_id),
        )
        cur.execute(
            "select status, decided_by_membership_id is not null, decided_at is not null "
            "from approval_step where id = %s",
            (step_id,),
        )
        assert cur.fetchone() == ("approved", True, True)


def test_owner_override_decider_may_differ_from_the_assignee(conn: object) -> None:
    # FR-007: an owner may decide a step assigned to someone else; the schema does not force
    # decided_by == assigned.
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-c4")
        approver = _make_member(cur, owner.tenant_id, "appr-c4-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        step_id = _make_pending_step(
            cur, owner.tenant_id, request_id, approver.membership_id
        )

        cur.execute(
            "update approval_step set status = 'rejected', "
            "decided_by_membership_id = %s, decided_at = now() where id = %s",
            (owner.membership_id, step_id),
        )
        cur.execute(
            "select assigned_membership_id <> decided_by_membership_id "
            "from approval_step where id = %s",
            (step_id,),
        )
        assert cur.fetchone() == (True,)


def test_only_one_approval_step_per_request(conn: object) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-one")
        approver = _make_member(cur, owner.tenant_id, "appr-one-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        _make_pending_step(cur, owner.tenant_id, request_id, approver.membership_id)

        with pytest.raises(psycopg.errors.UniqueViolation):
            _make_pending_step(
                cur, owner.tenant_id, request_id, owner.membership_id
            )


# ── approve / reject move the request and step together ───────────────


def test_approving_moves_request_and_step_to_approved(conn: object) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "appr-flow")
        approver = _make_member(cur, owner.tenant_id, "appr-flow-app", "approver")
        act_as(cur, owner)
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id)
        step_id = _make_pending_step(
            cur, owner.tenant_id, request_id, approver.membership_id
        )

        cur.execute(
            "update purchase_request set status = 'approved' "
            "where id = %s and status = 'submitted'",
            (request_id,),
        )
        cur.execute(
            "update approval_step set status = 'approved', comment = 'ok', "
            "decided_by_membership_id = %s, decided_at = now() "
            "where id = %s and status = 'pending'",
            (approver.membership_id, step_id),
        )
        cur.execute(
            "select pr.status, s.status, s.comment "
            "from purchase_request pr join approval_step s "
            "on s.purchase_request_id = pr.id where pr.id = %s",
            (request_id,),
        )
        assert cur.fetchone() == ("approved", "approved", "ok")


# ── approval_step_scoped_visibility (RESTRICTIVE) ─────────────────────


def _seed_step_for_visibility(
    cur: psycopg.Cursor,
) -> tuple[Workspace, Workspace, Workspace, Workspace, UUID]:
    owner = make_workspace(cur, "appr-vis")
    requester = _make_member(cur, owner.tenant_id, "appr-vis-req", "buyer")
    approver = _make_member(cur, owner.tenant_id, "appr-vis-app", "approver")
    other = _make_member(cur, owner.tenant_id, "appr-vis-other", "approver")
    act_as(cur, owner)
    branch_id = _make_branch(cur, owner)
    request_id = _make_submitted_request(cur, requester, branch_id)
    step_id = _make_pending_step(
        cur, owner.tenant_id, request_id, approver.membership_id
    )
    return owner, requester, approver, other, step_id


def test_the_assigned_approver_sees_their_own_step(conn: object) -> None:
    with conn.cursor() as cur:
        _owner, _requester, approver, _other, step_id = _seed_step_for_visibility(cur)
        act_as(cur, approver)
        cur.execute("select id from approval_step")
        assert cur.fetchall() == [(step_id,)]


def test_the_requester_sees_the_step_on_their_own_request(conn: object) -> None:
    with conn.cursor() as cur:
        _owner, requester, _approver, _other, step_id = _seed_step_for_visibility(cur)
        act_as(cur, requester)
        cur.execute("select id from approval_step")
        assert cur.fetchall() == [(step_id,)]


def test_the_owner_sees_every_step(conn: object) -> None:
    with conn.cursor() as cur:
        owner, _requester, _approver, _other, step_id = _seed_step_for_visibility(cur)
        act_as(cur, owner)
        cur.execute("select id from approval_step")
        assert cur.fetchall() == [(step_id,)]


def test_an_unrelated_member_sees_no_step_at_all(conn: object) -> None:
    with conn.cursor() as cur:
        _owner, _requester, _approver, other, _step_id = _seed_step_for_visibility(cur)
        act_as(cur, other)
        cur.execute("select count(*) from approval_step")
        assert cur.fetchone() == (0,)


def test_a_decided_step_is_still_visible_but_out_of_the_pending_queue(conn: object) -> None:
    with conn.cursor() as cur:
        owner, _requester, approver, _other, step_id = _seed_step_for_visibility(cur)
        act_as(cur, owner)
        cur.execute(
            "update approval_step set status = 'approved', "
            "decided_by_membership_id = %s, decided_at = now() where id = %s",
            (approver.membership_id, step_id),
        )
        act_as(cur, approver)
        cur.execute("select count(*) from approval_step where id = %s", (step_id,))
        assert cur.fetchone() == (1,)
        cur.execute(
            "select count(*) from approval_step "
            "where assigned_membership_id = %s and status = 'pending'",
            (approver.membership_id,),
        )
        assert cur.fetchone() == (0,)
