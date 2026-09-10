from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import PermissionDeniedError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import router as requests_router
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.schemas import (
    ApprovalDelegationCreate,
    ThresholdRuleCreate,
)
from procurepilot_api.modules.requests.service import RequestsService


class InsertQuery:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.payload: dict[str, object] | None = None

    def insert(self, payload: dict[str, object]) -> InsertQuery:
        self.payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[{**self.row, **(self.payload or {})}])


class FakeClient:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.queries: dict[str, InsertQuery] = {}

    def table(self, name: str) -> InsertQuery:
        query = InsertQuery(self.rows[name])
        self.queries[name] = query
        return query


def member(role: MemberRole = MemberRole.owner) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email=f"{role.value}@example.test",
        role=role,
    )


def threshold_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "branch_id": None,
        "min_amount": "0.0000",
        "max_amount": "500.0000",
        "currency": "GBP",
        "approver_membership_id": uuid4(),
        "created_by": uuid4(),
        "created_at": datetime(2026, 9, 10, tzinfo=UTC),
        "updated_at": None,
    }


def delegation_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "delegator_membership_id": uuid4(),
        "delegate_membership_id": uuid4(),
        "starts_on": date(2026, 9, 10),
        "ends_on": date(2026, 9, 20),
        "created_at": datetime(2026, 9, 10, tzinfo=UTC),
    }


def request_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "branch_id": uuid4(),
        "estimated_total_amount": "250.0000",
        "estimated_total_currency": "GBP",
    }


def test_create_threshold_rule_is_owner_only() -> None:
    service = RequestsService()
    non_owner = member(MemberRole.buyer)

    with pytest.raises(PermissionDeniedError):
        service.create_threshold_rule(
            bearer_token="token",
            member=non_owner,
            payload=ThresholdRuleCreate(
                min_amount="0.0000",
                max_amount="500.0000",
                currency="GBP",
                approver_membership_id=uuid4(),
            ),
        )


def test_create_threshold_rule_records_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = member()
    row = threshold_row()
    client = FakeClient({"threshold_rule": row})
    service = RequestsService()
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(requests_module, "authenticated_client", lambda _settings, _token: client)
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))

    result = service.create_threshold_rule(
        bearer_token="token",
        member=owner,
        payload=ThresholdRuleCreate(
            min_amount="0.0000",
            max_amount="500.0000",
            currency="GBP",
            approver_membership_id=row["approver_membership_id"],
        ),
    )

    assert result.currency == "GBP"
    assert client.queries["threshold_rule"].payload is not None
    assert recorded[0]["action"] == "requests.threshold_rule_created"


def test_create_delegation_defaults_to_current_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = member(MemberRole.approver)
    row = delegation_row()
    client = FakeClient({"approval_delegation": row})
    service = RequestsService()
    monkeypatch.setattr(requests_module, "authenticated_client", lambda _settings, _token: client)
    monkeypatch.setattr(service, "_record", lambda **_kwargs: None)

    service.create_approval_delegation(
        bearer_token="token",
        member=current,
        payload=ApprovalDelegationCreate(
            delegate_membership_id=row["delegate_membership_id"],
            starts_on=date(2026, 9, 10),
            ends_on=date(2026, 9, 20),
        ),
    )

    assert client.queries["approval_delegation"].payload is not None
    assert (
        client.queries["approval_delegation"].payload[
            "delegator_membership_id"
        ]
        == str(current.membership_id)
    )


def test_submit_routing_creates_pending_approval_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requester = member(MemberRole.buyer)
    approver_id = uuid4()
    row = request_row()
    step_id = uuid4()
    client = FakeClient(
        {
            "approval_step": {
                "id": step_id,
                "purchase_request_id": row["id"],
                "assigned_membership_id": approver_id,
                "source": "threshold_match",
                "status": "pending",
                "comment": None,
                "decided_by_membership_id": None,
                "decided_at": None,
            }
        }
    )
    service = RequestsService()
    monkeypatch.setattr(
        service,
        "_fetch_threshold_rules",
        lambda _client: [
            requests_module.ThresholdRuleRow(
                id=uuid4(),
                branch_id=None,
                min_amount=Decimal("0"),
                max_amount=None,
                currency="GBP",
                approver_membership_id=approver_id,
            )
        ],
    )
    monkeypatch.setattr(service, "_fetch_active_delegations", lambda _client, as_of: [])
    monkeypatch.setattr(service, "_fetch_removed_membership_ids", lambda _client: set())
    monkeypatch.setattr(service, "_fetch_owner_membership_id", lambda _client: uuid4())
    monkeypatch.setattr(service, "_record", lambda **_kwargs: None)

    result = service._create_submission_approval_step(  # noqa: SLF001
        client,
        bearer_token="token",
        member=requester,
        request_row=row,
    )

    assert result["assigned_membership_id"] == str(approver_id)
    assert client.queries["approval_step"].payload is not None
    assert client.queries["approval_step"].payload["status"] == "pending"


def test_threshold_router_passes_payload_to_service() -> None:
    payload = ThresholdRuleCreate(
        min_amount="0.0000",
        max_amount=None,
        currency="GBP",
        approver_membership_id=uuid4(),
    )
    captured: dict[str, object] = {}
    expected = object()
    fake_service = SimpleNamespace(
        create_threshold_rule=lambda **kwargs: captured.update(kwargs) or expected
    )

    result = requests_router.create_threshold_rule(
        payload=payload,
        token="token",
        member=member(),
        service=fake_service,
    )

    assert result is expected
    assert captured["payload"] is payload
