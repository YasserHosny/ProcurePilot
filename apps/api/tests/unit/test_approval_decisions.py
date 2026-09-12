from __future__ import annotations

from collections.abc import Callable
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
    decide_and_notify: Callable[..., tuple[dict, dict, UUID]] | None = None,
) -> tuple[RequestsService, FakeClient, list[dict[str, Any]]]:
    """Sets up a `RequestsService` with its PostgREST-facing reads mocked (pre-checks, response
    assembly) — everything this test file can meaningfully unit-test in isolation.

    `_decide_and_notify` (T037's own atomic-transaction write) is NOT mockable through
    `FakeClient` — it opens a real `psycopg` connection and needs a real Postgres, exactly like
    every other raw-psycopg-touching method in this codebase (devices/service.py's own tests live
    in tests/integration/, not here). Its correctness is proven for real in
    tests/integration/test_decision_atomicity.py. `decide_and_notify`, when given, replaces it
    with a fake so THIS test can still unit-test the surrounding orchestration (authorization,
    audit recording, enqueue call, response assembly) without touching a database.
    """
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
    monkeypatch.setattr(
        requests_module,
        "enqueue_push_job",
        lambda _settings, _notification_id: None,
    )
    if decide_and_notify is not None:
        monkeypatch.setattr(service, "_decide_and_notify", decide_and_notify)
    return service, client, recorded


def test_assigned_approver_can_approve_with_recorded_human_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, approver.membership_id)
    decided_request = {**req, "status": "approved"}
    decided_step = {
        **step,
        "status": "approved",
        "comment": "Approved",
        "decided_by_membership_id": str(approver.membership_id),
        "decided_at": "2026-09-12T12:00:00Z",
    }
    notification_id = uuid4()

    def fake_decide_and_notify(**kwargs: object) -> tuple[dict, dict, UUID]:
        assert kwargs["decision"] == "approved"
        assert kwargs["comment"] == "Approved"
        return decided_request, decided_step, notification_id

    service, _client, recorded = prepare_decision_service(
        monkeypatch,
        current_member=approver,
        req=req,
        step=step,
        decide_and_notify=fake_decide_and_notify,
    )

    result = service.approve_request(
        bearer_token="token",
        member=approver,
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Approved"),
    )

    assert result.status == "approved"
    assert result.approval_step is not None
    assert result.approval_step.status == "approved"
    assert result.approval_step.comment == "Approved"
    assert result.approval_step.decided_by_membership_id == approver.membership_id
    assert recorded[0]["action"] == "requests.approval_step_approved"


def test_owner_can_override_and_reject_pending_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    assigned_id = uuid4()
    owner = member(role=MemberRole.owner)
    req = request_row(request_id, uuid4())
    step = step_row(request_id, assigned_id)
    decided_request = {**req, "status": "rejected"}
    decided_step = {
        **step,
        "status": "rejected",
        "comment": "Need more context",
        "decided_by_membership_id": str(owner.membership_id),
        "decided_at": "2026-09-12T12:00:00Z",
    }
    notification_id = uuid4()

    service, _client, recorded = prepare_decision_service(
        monkeypatch,
        current_member=owner,
        req=req,
        step=step,
        decide_and_notify=lambda **_kwargs: (decided_request, decided_step, notification_id),
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
    # A withdrawal that flips the request out of `submitted` between the pre-check read and the
    # atomic write must not strand a `decided` step, a partially-applied request, or a
    # push_notification row — T037's transaction refuses the whole thing at once, and this test
    # verifies the SURROUNDING orchestration (no audit record, no enqueue call) correctly stops
    # when that happens. The transaction's own real all-or-nothing guarantee — not a mock — is
    # proven directly in tests/integration/test_decision_atomicity.py
    # (test_a_concurrent_withdrawal_leaves_the_step_pending), against a real concurrent write.
    request_id = uuid4()
    approver = member()
    req = request_row(request_id, uuid4())
    step = step_row(request_id, approver.membership_id)

    def raise_conflict(**_kwargs: object) -> tuple[dict, dict, UUID]:
        raise ConflictError(details={"reason": "not_submitted"})

    service, _client, recorded = prepare_decision_service(
        monkeypatch,
        current_member=approver,
        req=req,
        step=step,
        decide_and_notify=raise_conflict,
    )

    with pytest.raises(ConflictError) as exc:
        service.approve_request(
            bearer_token="token",
            member=approver,
            request_id=request_id,
            payload=ApprovalDecisionInput(comment="Approved"),
        )

    assert exc.value.details == {"reason": "not_submitted"}
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
