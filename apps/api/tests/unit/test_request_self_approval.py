"""Requester decisions are checked before transactional writes (ADR-024)."""

from uuid import uuid4

import pytest
from unit.test_approval_decisions import member, request_row, step_row

from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.service import RequestsService, _approval_step


class DecisionCursor:
    def __init__(self, request: dict, step: dict, owners: list) -> None:
        self.request, self.step, self.owners = request, step, owners
        self.query = ""
        self.writes = []

    def execute(self, query: str, params: object = None) -> None:
        self.query = query
        if query.lstrip().startswith("update"):
            self.writes.append(query)

    def fetchone(self) -> dict:
        return self.step if "approval_step" in self.query else self.request

    def fetchall(self) -> list[dict]:
        return [{"id": owner} for owner in self.owners]


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("role", [MemberRole.owner, MemberRole.approver])
def test_self_decision_is_refused_before_any_write(decision: str, role: MemberRole) -> None:
    actor = member(role=role)
    rid = uuid4()
    request = request_row(rid, actor.membership_id)
    step = step_row(rid, actor.membership_id)
    cur = DecisionCursor(request, step, [actor.membership_id, uuid4()])
    with pytest.raises(PermissionDeniedError) as error:
        RequestsService()._apply_request_decision(
            cur,
            member=actor,
            request_id=str(rid),
            step_id=str(step["id"]),
            decision=decision,
            request_status="ordered",
            comment="Reason",
            now="2026-11-03",
        )
    assert error.value.status_code == 403
    assert error.value.details == {"reason": "self_decision_not_allowed"}
    assert cur.writes == []


@pytest.mark.parametrize(
    "pending,assignee_self,decider_self,expected",
    [
        (True, True, False, True),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, True),
    ],
)
def test_self_approval_is_derived_from_current_step(
    pending: bool,
    assignee_self: bool,
    decider_self: bool,
    expected: bool,
) -> None:
    requester = uuid4()
    row = step_row(uuid4(), requester if assignee_self else uuid4())
    if not pending:
        row.update(
            status="approved", decided_by_membership_id=requester if decider_self else uuid4()
        )
    assert _approval_step(row, requester_membership_id=requester).self_approval is expected


@pytest.mark.parametrize("self_decision", [False, True])
def test_only_active_owner_or_another_requester_allows_writes(self_decision: bool) -> None:
    actor = member(role=MemberRole.owner)
    rid = uuid4()
    request = request_row(rid, actor.membership_id if self_decision else uuid4())
    step = step_row(rid, actor.membership_id)
    cur = DecisionCursor(request, step, [actor.membership_id])
    RequestsService()._apply_request_decision(
        cur,
        member=actor,
        request_id=str(rid),
        step_id=str(step["id"]),
        decision="approved",
        request_status="ordered",
        comment=None,
        now="2026-11-03",
    )
    assert len(cur.writes) == 2


def test_stale_authorization_precedes_self_decision_rule() -> None:
    from procurepilot_api.errors import ConflictError

    actor = member()
    rid = uuid4()
    cur = DecisionCursor(request_row(rid, actor.membership_id), step_row(rid, uuid4()), [uuid4()])
    with pytest.raises(ConflictError) as error:
        RequestsService()._apply_request_decision(
            cur,
            member=actor,
            request_id=str(rid),
            step_id=str(cur.step["id"]),
            decision="approved",
            request_status="ordered",
            comment=None,
            now="2026-11-03",
        )
    assert error.value.details == {"reason": "no_pending_approval"}
    assert cur.writes == []


def test_active_owner_lookup_reads_past_the_data_api_page_limit() -> None:
    from types import SimpleNamespace

    from unit.test_approval_decisions import SelectQuery

    owners = [uuid4() for _ in range(1001)]
    query = SelectQuery(
        [{"id": owner, "role": "owner", "status": "active"} for owner in owners]
        + [{"id": uuid4(), "role": "owner", "status": "removed"}]
    )
    client = SimpleNamespace(table=lambda _: query)
    assert RequestsService()._fetch_owner_membership_ids(client) == owners
    assert query.ranges == [(0, 999), (1000, 1999)]


@pytest.mark.parametrize("pending", [False, True])
def test_group_replay_derives_flag_for_snapshots_before_adr_024(pending: bool) -> None:
    from procurepilot_api.modules.requests.service import _replay_group_response

    requester, rid = uuid4(), uuid4()
    row = request_row(rid, requester)
    step = step_row(rid, requester)
    step["assigned_name"] = "Owner"
    if not pending:
        row["status"] = "ordered"
        step.update(status="approved", decided_by_membership_id=requester)
    row.update(lines=[], approval_step=step)
    response = _replay_group_response([row])[0]
    assert response.approval_step is not None
    assert response.approval_step.self_approval is True
    assert response.approval_step.assigned_name == "Owner"
