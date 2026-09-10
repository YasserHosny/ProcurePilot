from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.service import RequestsService


class ApprovalStepTable:
    """Minimal stand-in for ``client.table("approval_step")`` covering the one select and the
    per-row updates that ``escalate_pending_steps_for_removed_member`` issues."""

    def __init__(
        self,
        pending: list[dict[str, object]],
        *,
        update_results: list[list[dict[str, object]]] | None = None,
    ) -> None:
        self.pending = pending
        self._update_results = update_results
        self.update_calls: list[dict[str, Any]] = []
        self._payload: dict[str, object] | None = None
        self._filters: list[tuple[str, str]] = []

    def select(self, _columns: str) -> ApprovalStepTable:
        return self

    def update(self, payload: dict[str, object]) -> ApprovalStepTable:
        self._payload = payload
        return self

    def eq(self, column: str, value: object) -> ApprovalStepTable:
        self._filters.append((column, str(value)))
        return self

    def execute(self) -> SimpleNamespace:
        if self._payload is None:
            self._filters = []
            return SimpleNamespace(data=[dict(row) for row in self.pending])

        index = len(self.update_calls)
        self.update_calls.append(
            {"payload": self._payload, "filters": self._filters}
        )
        if self._update_results is not None:
            data = self._update_results[index]
        else:
            data = [{**self.pending[index], **self._payload}]
        self._payload = None
        self._filters = []
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self, step_table: ApprovalStepTable) -> None:
        self.step_table = step_table
        self.tables_requested: list[str] = []

    def table(self, name: str) -> ApprovalStepTable:
        self.tables_requested.append(name)
        assert name == "approval_step"
        return self.step_table


def actor() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )


def pending_step(request_id: UUID | None = None) -> dict[str, object]:
    return {
        "id": uuid4(),
        "purchase_request_id": request_id or uuid4(),
    }


def _prepare(
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_table: ApprovalStepTable,
    owner_id: UUID | None = None,
    owner_raises: bool = False,
) -> tuple[RequestsService, FakeClient, list[dict[str, Any]]]:
    client = FakeClient(step_table)
    service = RequestsService()
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        requests_module, "authenticated_client", lambda _settings, _token: client
    )

    def _fetch_owner(_client: object) -> UUID:
        if owner_raises:
            raise AssertionError("owner lookup should not run when nothing is pending")
        return owner_id or uuid4()

    monkeypatch.setattr(service, "_fetch_owner_membership_id", _fetch_owner)
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))
    return service, client, recorded


def test_escalates_every_pending_step_to_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    removed_id = uuid4()
    steps = [pending_step(), pending_step()]
    table = ApprovalStepTable(steps)
    service, _client, recorded = _prepare(
        monkeypatch, step_table=table, owner_id=owner_id
    )

    escalated = service.escalate_pending_steps_for_removed_member(
        bearer_token="token",
        actor=actor(),
        removed_membership_id=removed_id,
    )

    assert escalated == 2
    assert len(table.update_calls) == 2
    for call, step in zip(table.update_calls, steps, strict=True):
        assert call["payload"] == {
            "assigned_membership_id": str(owner_id),
            "source": "owner_fallback",
        }
        assert ("id", str(step["id"])) in call["filters"]
        assert ("status", "pending") in call["filters"]

    assert [r["action"] for r in recorded] == [
        "requests.approval_step_escalated",
        "requests.approval_step_escalated",
    ]
    assert recorded[0]["target"]["reason"] == "assigned_approver_removed"
    assert recorded[0]["target"]["assigned_membership_id"] == str(owner_id)
    assert recorded[0]["target"]["purchase_request_id"] == str(
        steps[0]["purchase_request_id"]
    )


def test_no_pending_steps_is_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = ApprovalStepTable([])
    service, _client, recorded = _prepare(
        monkeypatch, step_table=table, owner_raises=True
    )

    escalated = service.escalate_pending_steps_for_removed_member(
        bearer_token="token",
        actor=actor(),
        removed_membership_id=uuid4(),
    )

    assert escalated == 0
    assert table.update_calls == []
    assert recorded == []


def test_step_decided_concurrently_is_skipped_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The per-row update repeats the status = 'pending' guard; a decision landing first makes it
    # match zero rows, and that step is left as decided rather than force-reassigned.
    steps = [pending_step(), pending_step()]
    table = ApprovalStepTable(
        steps,
        update_results=[[], [{"id": str(steps[1]["id"])}]],
    )
    service, _client, recorded = _prepare(
        monkeypatch, step_table=table, owner_id=uuid4()
    )

    escalated = service.escalate_pending_steps_for_removed_member(
        bearer_token="token",
        actor=actor(),
        removed_membership_id=uuid4(),
    )

    assert escalated == 1
    assert len(table.update_calls) == 2
    assert len(recorded) == 1
    assert recorded[0]["target"]["approval_step_id"] == str(steps[1]["id"])
