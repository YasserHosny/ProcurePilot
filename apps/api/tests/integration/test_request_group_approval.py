"""US3: real RLS, transactions, outbox and HTTP guards, independent of split preparation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg import sql

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace, reset_role
from integration.test_confirm_delivery import _add_line, _payload
from integration.test_purchase_requests import _current_member, _make_member
from integration.test_request_group_read import api_as as read_api_as
from integration.test_request_group_schema import _insert_group, _setup
from procurepilot_api.modules.requests import service as service_module
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


@contextmanager
def api_as(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    ws: Workspace,
) -> Iterator[tuple[TestClient, RequestsService, list[str]]]:
    # Several actors use the API within one test; restore each actor's monkeypatches.
    with monkeypatch.context() as scoped:
        with read_api_as(conn, scoped, ws) as context:
            yield context


@dataclass
class Split:
    owner: Workspace
    requester: Workspace
    a: Workspace
    b: Workspace
    group: UUID
    requests: list[UUID]
    branch: UUID


def seed(conn: psycopg.Connection) -> Split:
    with conn.cursor() as cur:
        owner, branch, rfq, job = _setup(cur, "group-approval")
        requester, a, b = [
            _make_member(cur, owner.tenant_id, f"group-{role}-{uuid4().hex[:8]}", role)
            for role in ("buyer", "approver", "approver")
        ]
        group = _insert_group(cur, requester, branch, rfq, job)
        requests = [uuid4(), uuid4()]
        for request_id, amount in zip(requests, (2773, 1290), strict=True):
            cur.execute(
                "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
                "required_by_date,status,request_group_id,estimated_total_amount,"
                "estimated_total_currency,has_incomplete_estimate) "
                "values (%s,%s,%s,%s,current_date+7,'draft',%s,%s,'SAR',false)",
                (request_id, owner.tenant_id, branch, requester.membership_id, group, amount),
            )
        for approver, minimum, maximum in ((a, 0, 2000), (b, 2000, None)):
            cur.execute(
                "insert into threshold_rule (tenant_id,branch_id,min_amount,max_amount,currency,"
                "approver_membership_id,created_by) values (%s,%s,%s,%s,'SAR',%s,%s)",
                (
                    owner.tenant_id,
                    branch,
                    minimum,
                    maximum,
                    approver.membership_id,
                    owner.membership_id,
                ),
            )
    conn.commit()
    return Split(owner, requester, a, b, group, requests, branch)


def post(
    client: TestClient,
    data: Split,
    action: str,
    *,
    key: UUID | None = None,
    comment: str | None = "One decision",
) -> Response:
    return client.post(
        f"/api/v1/request-groups/{data.group}/{action}",
        headers={"Idempotency-Key": str(key or uuid4())},
        json={"comment": comment} if action in ("approve", "reject") else None,
    )


def assert_state(conn: psycopg.Connection, data: Split, status: str) -> None:
    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute("select status from purchase_request where request_group_id=%s", (data.group,))
        assert [row[0] for row in cur.fetchall()] == [status, status]
    conn.commit()


def submit(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, data: Split) -> None:
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        response = post(client, data, "submit")
        assert response.status_code == 200, response.text
        assert len(response.json()) == 2
        for request in response.json():
            assert request["status"] == "submitted"
            assert request["request_group"]["id"] == str(data.group)
            assert request["approval_step"]["assigned_membership_id"] == str(data.b.membership_id)
            assert request["approval_step"]["source"] == "group_threshold_match"
    assert_state(conn, data, "submitted")


def test_submit_and_approve_as_one_and_each_can_become_a_po(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn)
    enqueued = []
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda _, id_: enqueued.append(id_))
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.b) as (client, service, _queries):
        response = post(client, data, "approve")
        assert response.status_code == 200, response.text
        requests = response.json()
        assert {r["status"] for r in requests} == {"ordered"}
        steps = [r["approval_step"] for r in requests]
        assert len({s["decided_at"] for s in steps}) == 1
        assert {s["comment"] for s in steps} == {"One decision"}
        assert {s["decided_by_membership_id"] for s in steps} == {str(data.b.membership_id)}
        for request_id in data.requests:
            approved = service.validate_approved_request_for_order(
                bearer_token="token", member=_current_member(data.b, data.b), request_id=request_id
            )
            assert approved.status == "ordered"
    assert_state(conn, data, "ordered")
    with conn.cursor() as cur:
        cur.execute(
            "select member_id from push_notification where tenant_id=%s", (data.owner.tenant_id,)
        )
        assert cur.fetchall() == [(data.requester.membership_id,)]
        cur.execute(
            "select action from audit_event where tenant_id=%s order by id", (data.owner.tenant_id,)
        )
        assert [r[0] for r in cur.fetchall()] == [
            "requests.group_submitted",
            "requests.group_approved",
        ]
    assert len(enqueued) == 1


@pytest.mark.parametrize("action", ["confirm_delivery", "withdraw"])
def test_group_approved_requests_can_be_delivered_or_withdrawn(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        lines = [
            _add_line(cur, data.owner, request_id, quantity="2", name="Group delivery")
            for request_id in data.requests
        ]
    conn.commit()
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.b) as (client, _service, _queries):
        response = post(client, data, "approve")
        assert response.status_code == 200, response.text
    with api_as(conn, monkeypatch, data.requester) as (client, service, _queries):
        if action == "confirm_delivery":
            for request_id, line_id in zip(data.requests, lines, strict=True):
                delivered = service.confirm_delivery(
                    bearer_token="token",
                    member=_current_member(data.requester, data.requester),
                    request_id=request_id,
                    payload=_payload([(line_id, "2")]),
                )
                assert delivered.status == "delivered"
                assert delivered.has_delivery_discrepancy is False
                assert delivered.delivered_at is not None
                assert delivered.delivery_confirmed_by_membership_id == data.requester.membership_id
                assert delivered.lines[0].quantity_received == "2.000000"
        else:
            response = post(client, data, "withdraw")
            assert response.status_code == 200, response.text
    assert_state(conn, data, "delivered" if action == "confirm_delivery" else "withdrawn")


@pytest.mark.parametrize("action,status", [("reject", "rejected"), ("withdraw", "withdrawn")])
def test_reject_and_withdraw_apply_to_every_request(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str, status: str
) -> None:
    data = seed(conn)
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    submit(conn, monkeypatch, data)
    actor = data.b if action == "reject" else data.requester
    with api_as(conn, monkeypatch, actor) as (client, _service, _queries):
        response = post(client, data, action)
        assert response.status_code == 200, response.text
        if action == "reject":
            assert {r["approval_step"]["comment"] for r in response.json()} == {"One decision"}
    assert_state(conn, data, status)


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_approver_a_is_refused_without_partial_changes(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    data = seed(conn)
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.a) as (client, _service, _queries):
        response = post(client, data, action)
        assert response.status_code == 403, response.text
    assert_state(conn, data, "submitted")


@pytest.mark.parametrize("action", ["submit", "withdraw", "approve", "reject"])
def test_single_request_part_of_split_guard(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    data = seed(conn)
    if action in ("approve", "reject"):
        submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.owner) as (client, _service, _queries):
        response = client.post(
            f"/api/v1/requests/{data.requests[0]}/{action}", json={"comment": "reason"}
        )
        assert response.status_code == 409, response.text
        assert response.json()["details"] == {
            "reason": "part_of_split",
            "request_group_id": str(data.group),
        }
    assert_state(conn, data, "submitted" if action in ("approve", "reject") else "draft")


@pytest.mark.parametrize("field", ["branch_id", "lines"])
def test_patch_grouped_draft_is_refused_without_changing_group(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        branch = uuid4()
        cur.execute(
            "insert into branch (id,tenant_id,name) values (%s,%s,'Other branch')",
            (branch, data.owner.tenant_id),
        )
        line = _add_line(cur, data.owner, data.requests[0], quantity="2", name="Grouped draft")
        cur.execute("select workspace_product_id from purchase_request_line where id=%s", (line,))
        product = cur.fetchone()[0]
    conn.commit()

    def snapshot() -> list[object]:
        result = []
        with conn.cursor() as cur:
            reset_role(cur)
            for table in ("purchase_request_group", "purchase_request", "purchase_request_line"):
                cur.execute(
                    sql.SQL("select to_jsonb(t) from {} t where tenant_id=%s order by id").format(
                        sql.Identifier(table)
                    ),
                    (data.owner.tenant_id,),
                )
                result.append(cur.fetchall())
        conn.commit()
        return result

    before = snapshot()
    patch = (
        {"branch_id": str(branch)}
        if field == "branch_id"
        else {"lines": [{"workspace_product_id": str(product), "quantity": "9"}]}
    )
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        response = client.patch(f"/api/v1/requests/{data.requests[0]}", json=patch)
    after = snapshot()
    assert response.status_code == 409, response.text
    assert response.json()["details"] == {
        "reason": "part_of_split",
        "request_group_id": str(data.group),
    }
    assert after == before


@pytest.mark.parametrize("action", ["submit", "withdraw", "approve", "reject"])
def test_other_tenant_and_invisible_branch_get_404(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        stranger = make_workspace(cur, "group-stranger")
        scoped = _make_member(cur, data.owner.tenant_id, f"scoped-{uuid4().hex[:8]}", "buyer")
        branch = uuid4()
        cur.execute(
            "insert into branch (id,tenant_id,name) values (%s,%s,'Hidden')",
            (branch, data.owner.tenant_id),
        )
        cur.execute(
            "insert into branch_role_assignment (tenant_id,membership_id,branch_id) values "
            "(%s,%s,%s)",
            (data.owner.tenant_id, scoped.membership_id, branch),
        )
    conn.commit()
    for actor in (stranger, scoped):
        with api_as(conn, monkeypatch, actor) as (client, _service, _queries):
            response = post(client, data, action)
            assert response.status_code == 404, response.text
    assert_state(conn, data, "draft")


@pytest.mark.parametrize("action", ["approve", "reject", "withdraw"])
def test_idempotent_replay_returns_original_body_even_after_later_transition(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    data = seed(conn)
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    submit_key, decision_key = uuid4(), uuid4()
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        original = post(client, data, "submit", key=submit_key)
        assert original.status_code == 200, original.text
    actor = data.requester if action == "withdraw" else data.b
    with api_as(conn, monkeypatch, actor) as (client, _service, _queries):
        decision = post(client, data, action, key=decision_key)
        assert decision.status_code == 200, decision.text
        replay = post(client, data, action, key=decision_key)
        assert replay.status_code == 200, replay.text
        assert replay.json() == decision.json()
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        replay = post(client, data, "submit", key=submit_key)
        assert replay.status_code == 200, replay.text
        assert replay.json() == original.json()
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from approval_step where tenant_id=%s", (data.owner.tenant_id,)
        )
        assert cur.fetchone() == (2,)
        cur.execute(
            "select count(*) from push_notification where tenant_id=%s", (data.owner.tenant_id,)
        )
        assert cur.fetchone() == (0 if action == "withdraw" else 1,)


def test_rejection_requires_nonblank_comment(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = seed(conn)
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.b) as (client, _service, _queries):
        for comment in (None, "", "   "):
            response = post(client, data, "reject", comment=comment)
            assert response.status_code == 422, response.text
    assert_state(conn, data, "submitted")


@pytest.mark.parametrize(
    "action,reason",
    [("submit", "not_draft"), ("approve", "not_submitted"), ("reject", "not_submitted")],
)
def test_wrong_state_leaves_whole_group_unchanged(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch, action: str, reason: str
) -> None:
    data = seed(conn)
    if action == "submit":
        submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.owner) as (client, _service, _queries):
        response = post(client, data, action)
        assert response.status_code == 409, response.text
        assert response.json()["details"]["reason"] == reason
    assert_state(conn, data, "submitted" if action == "submit" else "draft")


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_owner_can_decide_the_whole_group(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    data = seed(conn)
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.owner) as (client, _service, _queries):
        response = post(client, data, action)
        assert response.status_code == 200, response.text
        assert {r["approval_step"]["decided_by_membership_id"] for r in response.json()} == {
            str(data.owner.membership_id)
        }
    assert_state(conn, data, "ordered" if action == "approve" else "rejected")


def test_draft_withdraw_and_requester_authorization(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = seed(conn)
    with api_as(conn, monkeypatch, data.a) as (client, _service, _queries):
        for action in ("submit", "withdraw"):
            assert post(client, data, action).status_code == 403
    assert_state(conn, data, "draft")
    with api_as(conn, monkeypatch, data.owner) as (client, _service, _queries):
        # Match single withdrawal: owner may withdraw another member's draft.
        response = post(client, data, "withdraw")
        assert response.status_code == 200, response.text
    assert_state(conn, data, "withdrawn")
    with conn.cursor() as cur:
        cur.execute("select action from audit_event where tenant_id=%s", (data.owner.tenant_id,))
        assert cur.fetchall() == [("requests.group_withdrawn",)]


def test_missing_idempotency_keys_and_oversized_comments_are_refused(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = seed(conn)
    with api_as(conn, monkeypatch, data.owner) as (client, _service, _queries):
        for action in ("submit", "approve", "reject", "withdraw"):
            response = client.post(f"/api/v1/request-groups/{data.group}/{action}", json={})
            assert response.status_code == 422
    submit(conn, monkeypatch, data)
    with api_as(conn, monkeypatch, data.b) as (client, _service, _queries):
        for action in ("approve", "reject"):
            response = post(client, data, action, comment="x" * 2001)
            assert response.status_code == 422, response.text
    assert_state(conn, data, "submitted")


@pytest.mark.parametrize(
    "stage", ["submit_step", "submit_escalation", "second_decision", "outbox", "audit"]
)
def test_a_database_failure_rolls_back_every_request_step_audit_and_outbox(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from procurepilot_api.errors import ServiceUnavailableError
    from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput

    data = seed(conn)
    submitting = stage.startswith("submit_")
    if stage == "submit_escalation":
        with conn.cursor() as cur:
            cur.execute("delete from threshold_rule where tenant_id=%s", (data.owner.tenant_id,))
        conn.commit()
    if not submitting:
        submit(conn, monkeypatch, data)
    real_connect = service_module.db.connect
    decisions = 0

    class FailingCursor(psycopg.Cursor):
        def execute(self, query: object, params: object = None, **kwargs: object) -> FailingCursor:
            nonlocal decisions
            result = super().execute(query, params, **kwargs)
            text = str(query)
            if "update approval_step" in text:
                decisions += 1
            fail = (
                (stage == "submit_step" and "insert into approval_step" in text)
                or (
                    stage == "submit_escalation"
                    and "select record_audit_event" in text
                    and params[0] == "requests.approval_step_escalated"
                )
                or (
                    stage == "second_decision" and "update approval_step" in text and decisions == 2
                )
                or (stage == "outbox" and "insert into push_notification" in text)
                or (stage == "audit" and "select record_audit_event" in text)
            )
            if fail:
                # A real PostgreSQL error AFTER the selected write, not a fake write result.
                super().execute("select 1/0")
            return result

    def connect(*args: object, **kwargs: object) -> psycopg.Connection:
        return real_connect(*args, cursor_factory=FailingCursor, **kwargs)

    monkeypatch.setattr(service_module.db, "connect", connect)
    service = RequestsService()
    with pytest.raises(ServiceUnavailableError):
        if submitting:
            service.submit_group(
                bearer_token="token",
                member=_current_member(data.requester, data.requester),
                group_id=data.group,
                idempotency_key=uuid4(),
            )
        else:
            service.approve_group(
                bearer_token="token",
                member=_current_member(data.b, data.b),
                group_id=data.group,
                idempotency_key=uuid4(),
                payload=ApprovalDecisionInput(comment="Atomic decision"),
            )
    assert_state(conn, data, "draft" if submitting else "submitted")
    with conn.cursor() as cur:
        cur.execute("select status from approval_step where tenant_id=%s", (data.owner.tenant_id,))
        assert cur.fetchall() == ([] if submitting else [("pending",), ("pending",)])
        cur.execute("select action from audit_event where tenant_id=%s", (data.owner.tenant_id,))
        assert cur.fetchall() == ([] if submitting else [("requests.group_submitted",)])
        cur.execute(
            "select count(*) from push_notification where tenant_id=%s", (data.owner.tenant_id,)
        )
        assert cur.fetchone() == (0,)


@pytest.mark.parametrize("other_action", ["reject", "withdraw", "approve_replay"])
def test_concurrent_actions_cannot_split_statuses_or_duplicate_notifications(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    other_action: str,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from procurepilot_api.errors import ConflictError
    from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput

    data = seed(conn)
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    submit(conn, monkeypatch, data)
    barrier = Barrier(2)
    key = uuid4()

    def act(action: str) -> tuple[int, list[dict[str, object]]]:
        service = RequestsService()
        member = data.requester if action == "withdraw" else data.b
        kwargs = dict(
            bearer_token="token",
            member=_current_member(member, member),
            group_id=data.group,
            idempotency_key=key,
        )
        if action != "withdraw":
            kwargs["payload"] = ApprovalDecisionInput(comment="Concurrent decision")
        barrier.wait(timeout=10)
        try:
            result = getattr(service, f"{action}_group")(**kwargs)
            return 200, [r.model_dump(mode="json") for r in result]
        except ConflictError:
            return 409, []

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(act, "approve")
        second = pool.submit(act, "approve" if other_action == "approve_replay" else other_action)
        outcomes = [first.result(timeout=20), second.result(timeout=20)]
    if other_action == "approve_replay":
        assert outcomes[0] == outcomes[1]
        assert outcomes[0][0] == 200
    elif other_action == "withdraw" and all(code == 200 for code, _ in outcomes):
        # Approval may serialize first: ordered requests remain withdrawable without a PO.
        assert {r["status"] for r in outcomes[0][1]} == {"ordered"}
        assert {r["status"] for r in outcomes[1][1]} == {"withdrawn"}
    else:
        assert sorted(code for code, _ in outcomes) == [200, 409]
    success = next(body for code, body in reversed(outcomes) if code == 200)
    assert len({r["status"] for r in success}) == 1
    status = success[0]["status"]
    assert_state(conn, data, status)
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from push_notification where tenant_id=%s", (data.owner.tenant_id,)
        )
        approval_succeeded = outcomes[0][0] == 200
        assert cur.fetchone() == (1 if approval_succeeded or other_action == "reject" else 0,)


def test_submission_without_matching_rule_assigns_both_steps_to_owner(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = seed(conn)
    with conn.cursor() as cur:
        cur.execute("delete from threshold_rule where tenant_id=%s", (data.owner.tenant_id,))
    conn.commit()
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        key = uuid4()
        response = post(client, data, "submit", key=key)
        assert response.status_code == 200, response.text
        assert {r["approval_step"]["assigned_membership_id"] for r in response.json()} == {
            str(data.owner.membership_id)
        }
        assert {r["approval_step"]["source"] for r in response.json()} == {"owner_fallback"}
        replay = post(client, data, "submit", key=key)
        assert replay.status_code == 200, replay.text
        assert replay.json() == response.json()
    with conn.cursor() as cur:
        reset_role(cur)
        cur.execute(
            "select target from audit_event where tenant_id=%s "
            "and action='requests.approval_step_escalated'",
            (data.owner.tenant_id,),
        )
        targets = [row[0] for row in cur.fetchall()]
        assert len(targets) == len(data.requests)
        assert {tuple(sorted(target.items())) for target in targets} == {
            tuple(
                sorted(
                    {
                        "purchase_request_id": request["id"],
                        "approval_step_id": request["approval_step"]["id"],
                        "assigned_membership_id": str(data.owner.membership_id),
                    }.items()
                )
            )
            for request in response.json()
        }
        # PostgreSQL stamps all rows from the same transaction with the same xmin.
        cur.execute(
            "select xmin::text from approval_step where tenant_id=%s union "
            "select xmin::text from audit_event where tenant_id=%s",
            (data.owner.tenant_id, data.owner.tenant_id),
        )
        assert len(cur.fetchall()) == 1


def test_budget_status_sees_both_just_submitted_requests_and_does_not_block_approval(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = seed(conn)
    monkeypatch.setattr(service_module, "enqueue_push_job", lambda *_: None)
    with conn.cursor() as cur:
        cur.execute(
            "insert into budget "
            "(tenant_id,amount,currency,period,period_start,scope,branch_id,created_by) "
            "values (%s,4000,'SAR','monthly',date_trunc('month',current_date+7),'branch',%s,%s)",
            (data.owner.tenant_id, data.branch, data.owner.membership_id),
        )
    conn.commit()
    with api_as(conn, monkeypatch, data.requester) as (client, _service, _queries):
        response = post(client, data, "submit")
        assert response.status_code == 200, response.text
        for request in response.json():
            assert request["budget_status"]["status"] == "over"
            assert request["budget_status"]["exceeds"] is True
            assert request["budget_status"]["remaining_amount"]["currency"] == "SAR"
    with api_as(conn, monkeypatch, data.b) as (client, _service, _queries):
        response = post(client, data, "approve")
        assert response.status_code == 200, response.text
        assert {r["budget_status"]["status"] for r in response.json()} == {"over"}
    assert_state(conn, data, "ordered")
