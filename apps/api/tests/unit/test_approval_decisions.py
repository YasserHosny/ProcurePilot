from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import router as requests_router
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService


class UpdateQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.payload: dict[str, object] | None = None
        self.filters: list[tuple[str, str]] = []

    def update(self, payload: dict[str, object]) -> UpdateQuery:
        self.payload = payload
        return self

    def eq(self, column: str, value: str) -> UpdateQuery:
        self.filters.append((column, value))
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[{**row, **(self.payload or {})} for row in self.rows])


class SelectQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, str]] = []
        self.ranges: list[tuple[int, int]] = []

    def select(self, _columns: str) -> SelectQuery:
        return self

    def eq(self, column: str, value: str) -> SelectQuery:
        self.filters.append((column, value))
        return self

    def order(self, *_args: object, **_kwargs: object) -> SelectQuery:
        return self

    def range(self, start: int, end: int) -> SelectQuery:
        self.ranges.append((start, end))
        return self

    def execute(self) -> SimpleNamespace:
        data = self.rows
        for column, value in self.filters:
            data = [row for row in data if str(row.get(column)) == value]
        if self.ranges:
            start, end = self.ranges[-1]
            data = data[start : end + 1]
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self, *, step_rows: list[dict[str, object]] | None = None) -> None:
        self.step_rows = step_rows or []
        self.updates: dict[str, UpdateQuery] = {}

    def table(self, name: str) -> SelectQuery | UpdateQuery:
        if name == "approval_step" and self.step_rows:
            return SelectQuery(self.step_rows)
        query = self.updates.setdefault(name, UpdateQuery([]))
        return query


def member(
    *,
    membership_id: UUID | None = None,
    role: MemberRole = MemberRole.approver,
) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id or uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="approver@example.test",
        role=role,
    )


def request_row(
    request_id: UUID,
    requester_id: UUID,
    *,
    status: str = "submitted",
) -> dict[str, object]:
    return {
        "id": request_id,
        "tenant_id": uuid4(),
        "branch_id": uuid4(),
        "cost_centre_id": None,
        "requested_by_membership_id": requester_id,
        "required_by_date": "2026-09-20",
        "status": status,
        "estimated_total_amount": "25.0000",
        "estimated_total_currency": "GBP",
        "has_incomplete_estimate": False,
        "submitted_at": "2026-09-10T08:00:00Z",
        "withdrawn_at": None,
        "created_at": "2026-09-10T08:00:00Z",
        "updated_at": "2026-09-10T08:00:00Z",
    }


def step_row(
    request_id: UUID,
    assigned_id: UUID,
    *,
    status: str = "pending",
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "purchase_request_id": request_id,
        "assigned_membership_id": assigned_id,
        "source": "owner_fallback",
        "status": status,
        "comment": None,
        "decided_by_membership_id": None,
        "decided_at": None,
    }


def line_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "purchase_request_id": uuid4(),
        "workspace_product_id": uuid4(),
        "quantity": "2.000000",
        "note": "needed",
        "estimated_unit_price_amount": "12.5000",
        "estimated_unit_price_currency": "GBP",
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": "2026-09-10T08:00:00Z",
    }


def prepare_decision_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    current_member: CurrentMember,
    req: dict[str, object],
    step: dict[str, object] | None,
) -> tuple[RequestsService, FakeClient, list[dict[str, Any]]]:
    client = FakeClient()
    client.updates["approval_step"] = UpdateQuery([step] if step else [])
    client.updates["purchase_request"] = UpdateQuery([req])
    service = RequestsService()
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(requests_module, "authenticated_client", lambda _settings, _token: client)
    monkeypatch.setattr(service, "_fetch_request", lambda _client, _id: req)
    monkeypatch.setattr(service, "_fetch_step", lambda _client, _id: step)
    monkeypatch.setattr(service, "_fetch_lines_for", lambda _client, _id: [line_row()])
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))
    return service, client, recorded


def test_assigned_approver_can_approve_with_recorded_human_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, approver.membership_id)
    service, client, recorded = prepare_decision_service(
        monkeypatch, current_member=approver, req=req, step=step
    )

    result = service.approve_request(
        bearer_token="token",
        member=approver,
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Approved"),
    )

    step_update = client.updates["approval_step"].payload
    request_update = client.updates["purchase_request"].payload
    assert result.status == "approved"
    assert result.approval_step is not None
    assert result.approval_step.decided_by_membership_id == approver.membership_id
    assert step_update is not None
    assert step_update["status"] == "approved"
    assert step_update["comment"] == "Approved"
    assert step_update["decided_by_membership_id"] == str(approver.membership_id)
    assert step_update["decided_at"] is not None
    assert request_update is not None
    assert request_update["status"] == "approved"
    assert recorded[0]["action"] == "requests.approval_step_approved"


def test_owner_can_override_and_reject_pending_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    assigned_id = uuid4()
    owner = member(role=MemberRole.owner)
    req = request_row(request_id, uuid4())
    step = step_row(request_id, assigned_id)
    service, _client, recorded = prepare_decision_service(
        monkeypatch, current_member=owner, req=req, step=step
    )

    result = service.reject_request(
        bearer_token="token",
        member=owner,
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Need more context"),
    )

    assert result.status == "rejected"
    assert result.approval_step is not None
    assert result.approval_step.decided_by_membership_id == owner.membership_id
    assert recorded[0]["action"] == "requests.approval_step_rejected"


def test_unassigned_member_cannot_decide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    current = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, uuid4())
    service, _client, _recorded = prepare_decision_service(
        monkeypatch, current_member=current, req=req, step=step
    )

    with pytest.raises(PermissionDeniedError) as exc:
        service.approve_request(
            bearer_token="token",
            member=current,
            request_id=request_id,
            payload=ApprovalDecisionInput(),
        )

    assert exc.value.details == {"reason": "not_assigned_approver"}


def test_non_submitted_request_cannot_be_decided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4(), status="draft")
    step = step_row(request_id, approver.membership_id)
    service, _client, _recorded = prepare_decision_service(
        monkeypatch, current_member=approver, req=req, step=step
    )

    with pytest.raises(ConflictError) as exc:
        service.approve_request(
            bearer_token="token",
            member=approver,
            request_id=request_id,
            payload=ApprovalDecisionInput(),
        )

    assert exc.value.details == {"reason": "not_submitted"}


def test_decided_step_cannot_be_decided_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, approver.membership_id, status="approved")
    service, _client, _recorded = prepare_decision_service(
        monkeypatch, current_member=approver, req=req, step=step
    )

    with pytest.raises(ConflictError) as exc:
        service.reject_request(
            bearer_token="token",
            member=approver,
            request_id=request_id,
            payload=ApprovalDecisionInput(),
        )

    assert exc.value.details == {"reason": "no_pending_approval"}


def test_concurrent_withdrawal_leaves_step_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A withdrawal that flips the request out of `submitted` between the early guard and the
    # write must not strand a `decided` step on a non-submitted request. The request is updated
    # first under a `status = 'submitted'` guard; when that matches zero rows we raise before
    # touching the step, so the step's payload is never set.
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, approver.membership_id)
    service, client, recorded = prepare_decision_service(
        monkeypatch, current_member=approver, req=req, step=step
    )
    client.updates["purchase_request"] = UpdateQuery([])

    with pytest.raises(ConflictError) as exc:
        service.approve_request(
            bearer_token="token",
            member=approver,
            request_id=request_id,
            payload=ApprovalDecisionInput(comment="Approved"),
        )

    assert exc.value.details == {"reason": "not_submitted"}
    assert client.updates["approval_step"].payload is None
    assert recorded == []


def test_pending_queue_filters_non_owner_to_their_assigned_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    current = member()
    own_step = step_row(request_id, current.membership_id)
    other_step = step_row(uuid4(), uuid4())
    client = FakeClient(step_rows=[own_step, other_step])
    service = RequestsService()
    monkeypatch.setattr(requests_module, "authenticated_client", lambda _settings, _token: client)
    monkeypatch.setattr(
        service,
        "_fetch_requests_batch",
        lambda _client, _ids: [request_row(request_id, uuid4())],
    )
    monkeypatch.setattr(
        service,
        "_fetch_lines_batch",
        lambda _client, _ids: {str(request_id): [line_row()]},
    )
    monkeypatch.setattr(service, "_budget_status_for", lambda _client, _row: None)

    result = service.list_pending_approvals(
        bearer_token="token", member=current
    )

    assert len(result.items) == 1
    assert result.items[0].approval_step is not None
    assert result.items[0].approval_step.assigned_membership_id == current.membership_id


def test_approval_router_passes_decision_payload_to_service() -> None:
    request_id = uuid4()
    payload = ApprovalDecisionInput(comment="Fine")
    captured: dict[str, object] = {}
    expected = object()
    fake_service = SimpleNamespace(
        approve_request=lambda **kwargs: captured.update(kwargs) or expected
    )

    result = requests_router.approve_request(
        request_id=request_id,
        payload=payload,
        token="token",
        member=member(),
        service=fake_service,
    )

    assert result is expected
    assert captured["request_id"] == request_id
    assert captured["payload"] is payload


def test_pending_router_passes_member_and_pagination_to_service() -> None:
    captured: dict[str, object] = {}
    expected = object()
    current = member()
    fake_service = SimpleNamespace(
        list_pending_approvals=lambda **kwargs: captured.update(kwargs) or expected
    )

    result = requests_router.list_pending_approvals(
        token="token",
        member=current,
        service=fake_service,
        cursor="abc",
        limit=25,
    )

    assert result is expected
    assert captured == {
        "bearer_token": "token",
        "member": current,
        "cursor": "abc",
        "limit": 25,
    }
