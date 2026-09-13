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
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the mobile migrations applied",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


class _Secret:
    def get_secret_value(self) -> str:
        return TEST_DATABASE_URL or ""


class _Settings:
    database_url = _Secret()
    redis_url = "redis://unit-test"


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


def _seed_decision_context(
    conn: psycopg.Connection, label: str, decision: str
) -> tuple[
    Workspace,
    Workspace,
    Workspace,
    UUID,
    UUID,
    dict[str, object],
    dict[str, object],
]:
    with conn.cursor() as cur:
        owner = make_workspace(cur, label)
        requester = _make_member(
            cur,
            owner.tenant_id,
            f"{label}-requester",
            "branch_manager",
        )
        approver = _make_member(cur, owner.tenant_id, f"{label}-approver", "approver")
        branch_id = _make_branch(cur, owner)
        request_id = _make_submitted_request(cur, owner, branch_id, requester)
        step_id = _make_pending_step(cur, owner, request_id, approver)
    conn.commit()

    request_row = {
        "id": request_id,
        "tenant_id": owner.tenant_id,
        "branch_id": branch_id,
        "cost_centre_id": None,
        "requested_by_membership_id": requester.membership_id,
        "required_by_date": "2026-09-19",
        "status": "submitted",
        "estimated_total_amount": None,
        "estimated_total_currency": None,
        "has_incomplete_estimate": False,
        "submitted_at": "2026-09-12T10:00:00Z",
        "withdrawn_at": None,
        "created_at": "2026-09-12T10:00:00Z",
        "updated_at": "2026-09-12T10:00:00Z",
    }
    step_row = {
        "id": step_id,
        "purchase_request_id": request_id,
        "assigned_membership_id": approver.membership_id,
        "source": "threshold_match",
        "status": "pending",
        "comment": None,
        "decided_by_membership_id": None,
        "decided_at": None,
    }
    assert decision in {"approved", "rejected"}
    return owner, requester, approver, request_id, step_id, request_row, step_row


def _prepare_service(
    monkeypatch: pytest.MonkeyPatch,
    request_row: dict[str, object],
    step_row: dict[str, object],
) -> RequestsService:
    service = RequestsService(settings=_Settings())  # type: ignore[arg-type]
    monkeypatch.setattr(requests_module, "authenticated_client", lambda *_args: object())
    monkeypatch.setattr(service, "_fetch_request", lambda *_args: request_row)
    monkeypatch.setattr(service, "_fetch_step", lambda *_args: step_row)
    monkeypatch.setattr(service, "_fetch_lines_for", lambda *_args: [])
    monkeypatch.setattr(service, "_budget_status_for", lambda *_args: None)
    monkeypatch.setattr(service, "_record", lambda **_kwargs: None)
    return service


def _push_rows(
    conn: psycopg.Connection, request_id: UUID
) -> list[tuple[UUID, str, UUID, UUID]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, status, purchase_request_id, member_id
            from push_notification
            where purchase_request_id = %s
            order by created_at, id
            """,
            (request_id,),
        )
        return list(cur.fetchall())


def test_decision_writes_one_queued_push_notification_and_enqueues_it(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, requester, approver, request_id, _step_id, request_row, step_row = (
        _seed_decision_context(conn, "t035-approve-enqueue", "approved")
    )
    enqueued: list[UUID] = []
    service = _prepare_service(monkeypatch, request_row, step_row)
    monkeypatch.setattr(
        requests_module,
        "enqueue_push_job",
        lambda _settings, notification_id: enqueued.append(notification_id),
    )

    result = service._decide_request(
        bearer_token="unused",
        member=_current_member(owner, approver, MemberRole.approver),
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Approved"),
        decision="approved",
    )

    # Lands on "ordered", not "approved" (chunk R2.3, research.md R1) — the push-notification
    # write-and-enqueue behavior this test exists to prove is unaffected by that status value.
    assert result.status == "ordered"
    rows = _push_rows(conn, request_id)
    assert len(rows) == 1
    notification_id, status, row_request_id, member_id = rows[0]
    assert status == "queued"
    assert row_request_id == request_id
    assert member_id == requester.membership_id
    assert enqueued == [notification_id]


def test_decision_push_notification_survives_enqueue_failure(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, requester, approver, request_id, _step_id, request_row, step_row = (
        _seed_decision_context(conn, "t035-reject-enqueue-fail", "rejected")
    )
    attempted: list[UUID] = []
    service = _prepare_service(monkeypatch, request_row, step_row)

    def fail_enqueue(_settings: object, notification_id: UUID) -> None:
        attempted.append(notification_id)
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(requests_module, "enqueue_push_job", fail_enqueue)

    result = service._decide_request(
        bearer_token="unused",
        member=_current_member(owner, approver, MemberRole.approver),
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Rejected"),
        decision="rejected",
    )

    assert result.status == "rejected"
    rows = _push_rows(conn, request_id)
    assert len(rows) == 1
    notification_id, status, row_request_id, member_id = rows[0]
    assert status == "queued"
    assert row_request_id == request_id
    assert member_id == requester.membership_id
    assert attempted == [notification_id]
