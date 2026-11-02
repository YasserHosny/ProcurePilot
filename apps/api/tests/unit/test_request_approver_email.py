from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from procurepilot_api.modules.requests.service import MemberContact, RequestsService


class FailingMembershipClient:
    def table(self, name: str) -> None:
        assert name == "membership"
        raise RuntimeError("membership lookup unavailable")


def test_approver_lookup_failure_returns_request_with_null_email(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service = RequestsService()
    monkeypatch.setattr(service, "_budget_status_for", lambda *_: None)
    monkeypatch.setattr(service, "_quoted_prices_for", lambda *_: {})
    request_row = {
        "id": uuid4(),
        "branch_id": uuid4(),
        "requested_by_membership_id": uuid4(),
        "required_by_date": "2026-10-10",
        "status": "submitted",
        "created_at": datetime.now(UTC),
    }
    step_row = {
        "id": uuid4(),
        "assigned_membership_id": uuid4(),
        "source": "owner_fallback",
        "status": "pending",
    }
    result = service._purchase_request_with_budget_status(
        FailingMembershipClient(), request_row, [], step_row, auto_prepared_lookup=False
    )
    assert result.id == request_row["id"]
    assert result.requester_email is None
    assert result.approval_step is not None
    assert result.approval_step.assigned_email is None
    assert result.approval_step.assigned_name is None
    assert "email lookup failed" in caplog.text


def test_member_contact_batch_queries_requesters_and_assignees_once() -> None:
    requester_id, assigned_id = str(uuid4()), str(uuid4())

    class MembershipClient:
        def __init__(self) -> None:
            self.queries = 0

        def table(self, name: str) -> MembershipClient:
            assert name == "membership"
            self.queries += 1
            return self

        def select(self, columns: str) -> MembershipClient:
            assert columns == "id,email,display_name"
            return self

        def in_(self, column: str, values: list[str]) -> MembershipClient:
            assert column == "id"
            assert set(values) == {requester_id, assigned_id}
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(
                data=[
                    {"id": requester_id, "email": "requester@example.test", "display_name": "سارة"},
                    {"id": assigned_id, "email": "approver@example.test", "display_name": None},
                ]
            )

    client = MembershipClient()
    emails = RequestsService()._fetch_member_contacts_batch(
        client,
        [{"requested_by_membership_id": requester_id}] * 3,
        [{"assigned_membership_id": assigned_id}] * 3,
    )
    assert client.queries == 1
    assert emails == {
        requester_id: MemberContact("requester@example.test", "سارة"),
        assigned_id: MemberContact("approver@example.test", None),
    }


def test_member_contact_batch_skips_missing_approval_step() -> None:
    requester_id = str(uuid4())

    class MembershipClient:
        def __init__(self) -> None:
            self.queries = 0

        def table(self, name: str) -> MembershipClient:
            assert name == "membership"
            self.queries += 1
            return self

        def select(self, columns: str) -> MembershipClient:
            assert columns == "id,email,display_name"
            return self

        def in_(self, column: str, values: list[str]) -> MembershipClient:
            assert column == "id"
            assert values == [requester_id]
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=[{"id": requester_id, "email": "requester@example.test"}])

    client = MembershipClient()
    emails = RequestsService()._fetch_member_contacts_batch(
        client, [{"requested_by_membership_id": requester_id}], [None]
    )
    assert client.queries == 1
    assert emails == {requester_id: MemberContact("requester@example.test", None)}
