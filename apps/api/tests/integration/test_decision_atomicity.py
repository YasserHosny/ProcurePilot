"""Direct-transaction tests for RequestsService._decide_and_notify — T037 (009-mobile-app-mvp).

Moved here from tests/unit/test_approval_decisions.py: that file's `FakeClient` mocked the
PostgREST-style `.update(...).eq(...).execute()` calls the *old* (non-atomic, review-flagged)
implementation made. T037 replaced those writes with a single raw-psycopg transaction (mirroring
devices/service.py's own pattern, since push_notification grants nothing to `authenticated` at
all) — that write path is no longer mockable through the PostgREST fake, so it needs a real
Postgres, exactly like every other raw-psycopg-touching test in this codebase (test_devices.py).

These tests call `_decide_and_notify()` directly rather than the public `approve_request()`/
`reject_request()` methods: those methods' own PRE-checks (`_fetch_request`/`_fetch_step`) go
through `authenticated_client()`, which needs a real running Supabase/PostgREST server — not
available in this bare-Postgres harness (the same limitation this project has hit and documented
repeatedly this session, e.g. T020/T025). `_decide_and_notify` itself needs only real Postgres, so
it is the one part of this method actually testable here — and it is the part T037 changed.
Authorization/orchestration logic around it (unchanged by T037) is still unit-tested with mocks in
tests/unit/test_approval_decisions.py.
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
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the R2.1/R2.2 migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


def _make_member(cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str) -> Workspace:
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


def _make_branch(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,'Main','GB')",
        (branch_id, workspace.tenant_id),
    )
    return branch_id


def _make_submitted_request(
    cur: psycopg.Cursor, workspace: Workspace, branch_id: UUID, requester: Workspace
) -> UUID:
    request_id = uuid4()
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status) "
        "values (%s,%s,%s,%s,current_date + interval '7 days','submitted')",
        (request_id, workspace.tenant_id, branch_id, requester.membership_id),
    )
    return request_id


def _make_pending_step(
    cur: psycopg.Cursor, workspace: Workspace, request_id: UUID, assigned: Workspace
) -> UUID:
    step_id = uuid4()
    cur.execute(
        "insert into approval_step "
        "(id,tenant_id,purchase_request_id,assigned_membership_id,source,status) "
        "values (%s,%s,%s,%s,'threshold_match','pending')",
        (step_id, workspace.tenant_id, request_id, assigned.membership_id),
    )
    return step_id


def _current_member(workspace: Workspace, member_ws: Workspace, role: MemberRole) -> CurrentMember:
    return CurrentMember(
        membership_id=member_ws.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=member_ws.user_id,
        email=f"{member_ws.label}@example.test",
        role=role,
    )


def test_a_real_decision_commits_all_three_writes_atomically(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "t037-approve")
        requester = _make_member(cur, owner.tenant_id, "t037-approve-requester", "branch_manager")
        approver = _make_member(cur, owner.tenant_id, "t037-approve-approver", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, approver)
    conn.commit()

    svc = RequestsService()
    decided_request, decided_step, notification_id = svc._decide_and_notify(
        member=_current_member(owner, approver, MemberRole.approver),
        request_id=str(request_id),
        step_id=str(step_id),
        decision="approved",
        comment="Approved",
        now="2026-09-12T12:00:00Z",
    )

    assert decided_request["status"] == "approved"
    assert decided_step["status"] == "approved"
    assert decided_step["comment"] == "Approved"
    assert str(decided_step["decided_by_membership_id"]) == str(approver.membership_id)
    assert notification_id is not None

    with conn.cursor() as cur:
        cur.execute("select status from purchase_request where id = %s", (request_id,))
        assert cur.fetchone() == ("approved",)
        cur.execute(
            "select status, decided_by_membership_id from approval_step where id = %s",
            (step_id,),
        )
        row = cur.fetchone()
        assert row[0] == "approved"
        assert str(row[1]) == str(approver.membership_id)
        cur.execute(
            "select member_id from push_notification where purchase_request_id = %s",
            (request_id,),
        )
        notif = cur.fetchone()
        assert notif is not None
        assert str(notif[0]) == str(requester.membership_id), (
            "push_notification.member_id must be the REQUESTER, not the decider"
        )


def test_owner_can_override_and_reject_pending_request(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "t037-owner-override")
        requester = _make_member(cur, owner.tenant_id, "t037-owner-requester", "branch_manager")
        assigned = _make_member(cur, owner.tenant_id, "t037-owner-assigned", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, assigned)
    conn.commit()

    svc = RequestsService()
    decided_request, decided_step, _notification_id = svc._decide_and_notify(
        member=_current_member(owner, owner, MemberRole.owner),
        request_id=str(request_id),
        step_id=str(step_id),
        decision="rejected",
        comment="Need more context",
        now="2026-09-12T12:00:00Z",
    )

    assert decided_request["status"] == "rejected"
    assert decided_step["status"] == "rejected"
    assert str(decided_step["decided_by_membership_id"]) == str(owner.membership_id)


def test_a_concurrent_withdrawal_leaves_the_step_pending(conn: psycopg.Connection) -> None:
    """A real race: the request is withdrawn (by a second, concurrent actor) between the
    pre-check read and the atomic decision transaction. The transaction's own
    `WHERE status = 'submitted'` guard — not a mock — must refuse, and must not have touched
    approval_step or written a push_notification row."""
    with conn.cursor() as cur:
        owner = make_workspace(cur, "t037-race")
        requester = _make_member(cur, owner.tenant_id, "t037-race-requester", "branch_manager")
        approver = _make_member(cur, owner.tenant_id, "t037-race-approver", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, approver)
    conn.commit()

    # Simulate the concurrent withdrawal directly — a separate connection/transaction, already
    # committed by the time the decision below runs.
    with psycopg.connect(TEST_DATABASE_URL or "") as other_conn:
        with other_conn.cursor() as other_cur:
            other_cur.execute(
                "update purchase_request set status = 'withdrawn' where id = %s",
                (request_id,),
            )

    svc = RequestsService()
    with pytest.raises(ConflictError) as exc:
        svc._decide_and_notify(
            member=_current_member(owner, approver, MemberRole.approver),
            request_id=str(request_id),
            step_id=str(step_id),
            decision="approved",
            comment="Approved",
            now="2026-09-12T13:00:00Z",
        )
    assert exc.value.details == {"reason": "not_submitted"}

    with conn.cursor() as cur:
        cur.execute("select status from approval_step where id = %s", (step_id,))
        assert cur.fetchone() == ("pending",)
        cur.execute(
            "select count(*) from push_notification where purchase_request_id = %s",
            (request_id,),
        )
        assert cur.fetchone() == (0,)
        cur.execute("select status from purchase_request where id = %s", (request_id,))
        assert cur.fetchone() == ("withdrawn",), "the concurrent withdrawal itself must stand"


def test_a_step_reassigned_after_the_precheck_refuses_the_stale_approver(
    conn: psycopg.Connection,
) -> None:
    """TOCTOU authorization gap (review finding): the pre-check in `_decide_request()` confirms
    the caller is the assigned approver, but that read happens before this transaction opens. If
    the step is reassigned in between (e.g. `escalate_pending_steps_for_removed_member` runs
    because the original approver was just removed from the workspace), the now-stale approver's
    decision must not still apply. The transactional UPDATE's own WHERE clause — not just the
    earlier Python-level check — must catch this."""
    with conn.cursor() as cur:
        owner = make_workspace(cur, "t037-reassign")
        requester = _make_member(cur, owner.tenant_id, "t037-reassign-requester", "branch_manager")
        original_approver = _make_member(
            cur, owner.tenant_id, "t037-reassign-original", "approver"
        )
        new_approver = _make_member(cur, owner.tenant_id, "t037-reassign-new", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, original_approver)
    conn.commit()

    # Simulate the step being reassigned (escalated to a different approver) after the caller's
    # own pre-check already read the OLD assignment — a separate, already-committed connection.
    with psycopg.connect(TEST_DATABASE_URL or "") as other_conn:
        with other_conn.cursor() as other_cur:
            other_cur.execute(
                "update approval_step set assigned_membership_id = %s where id = %s",
                (new_approver.membership_id, step_id),
            )

    svc = RequestsService()
    with pytest.raises(ConflictError) as exc:
        svc._decide_and_notify(
            member=_current_member(owner, original_approver, MemberRole.approver),
            request_id=str(request_id),
            step_id=str(step_id),
            decision="approved",
            comment="Approved",
            now="2026-09-12T14:00:00Z",
        )
    assert exc.value.details == {"reason": "no_pending_approval"}

    with conn.cursor() as cur:
        cur.execute(
            "select status, assigned_membership_id from approval_step where id = %s",
            (step_id,),
        )
        status, assigned = cur.fetchone()
        assert status == "pending", "must not have been decided by the now-stale approver"
        assert str(assigned) == str(new_approver.membership_id), "reassignment must stand"
        cur.execute("select status from purchase_request where id = %s", (request_id,))
        assert cur.fetchone() == ("submitted",)
        cur.execute(
            "select count(*) from push_notification where purchase_request_id = %s",
            (request_id,),
        )
        assert cur.fetchone() == (0,)


def test_the_new_approver_can_decide_after_a_reassignment(conn: psycopg.Connection) -> None:
    """The flip side of the above: once reassigned, the NEW approver's decision must succeed —
    this proves the fix adds a real authorization check, not just a blanket refusal."""
    with conn.cursor() as cur:
        owner = make_workspace(cur, "t037-reassign-ok")
        requester = _make_member(
            cur, owner.tenant_id, "t037-reassign-ok-requester", "branch_manager"
        )
        original_approver = _make_member(
            cur, owner.tenant_id, "t037-reassign-ok-original", "approver"
        )
        new_approver = _make_member(cur, owner.tenant_id, "t037-reassign-ok-new", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, original_approver)
        cur.execute(
            "update approval_step set assigned_membership_id = %s where id = %s",
            (new_approver.membership_id, step_id),
        )
    conn.commit()

    svc = RequestsService()
    decided_request, decided_step, notification_id = svc._decide_and_notify(
        member=_current_member(owner, new_approver, MemberRole.approver),
        request_id=str(request_id),
        step_id=str(step_id),
        decision="approved",
        comment="Approved by the new approver",
        now="2026-09-12T14:00:00Z",
    )
    assert decided_request["status"] == "approved"
    assert decided_step["status"] == "approved"
    assert str(decided_step["decided_by_membership_id"]) == str(new_approver.membership_id)
    assert notification_id is not None
