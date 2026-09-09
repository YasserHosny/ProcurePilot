from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching import resolution_service as resolution_module
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.schemas import (
    MatchDecision,
    MatchResolutionRequest,
    ProductSummary,
)
from procurepilot_api.modules.matching.service import MatchingService


class InsertQuery:
    def __init__(self, response_row: dict[str, object]) -> None:
        self.response_row = response_row
        self.payload: dict[str, object] | None = None

    def insert(self, payload: dict[str, object]) -> InsertQuery:
        self.payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[self.response_row])


class InsertClient:
    def __init__(self, response_row: dict[str, object]) -> None:
        self.query = InsertQuery(response_row)

    def table(self, _name: str) -> InsertQuery:
        return self.query


def member() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def test_task_routing_records_append_only_audit_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotation_id, line_id, task_id = uuid4(), uuid4(), uuid4()
    service = MatchingService()
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(matching_module, "_open_task_for_line", lambda _client, _id: None)
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))

    service._create_task(  # noqa: SLF001
        InsertClient({"id": task_id, "priority": "normal"}),
        member(),
        {"id": line_id, "quotation_id": quotation_id},
        reason="low_confidence",
        bearer_token="token",
    )

    assert recorded[0]["action"] == "matching.task_routed"
    assert recorded[0]["target"] == {
        "quotation_id": str(quotation_id),
        "quotation_line_id": str(line_id),
        "match_task_id": str(task_id),
        "reason": "low_confidence",
        "priority": "normal",
    }


def test_automatic_acceptance_records_decision_and_scoring_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotation_id, line_id, decision_id, candidate_id, product_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    service = MatchingService()
    service._landed_cost = SimpleNamespace(  # type: ignore[assignment] # test double
        compute_for_line_with_client=lambda **_kwargs: None
    )
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))

    service._create_automatic_decision(  # noqa: SLF001
        InsertClient({"id": decision_id}),
        member(),
        {"id": line_id, "quotation_id": quotation_id},
        {
            "id": candidate_id,
            "candidate_workspace_product_id": product_id,
            "confidence": "0.9500",
            "scoring_version": "matching-v1",
        },
        bearer_token="token",
    )

    target = recorded[0]["target"]
    assert recorded[0]["action"] == "matching.auto_accepted"
    assert target["quotation_id"] == str(quotation_id)
    assert target["decision_id"] == str(decision_id)
    assert target["candidate_id"] == str(candidate_id)
    assert target["score"] == "0.9500"
    assert target["scoring_version"] == "matching-v1"


def test_human_resolution_records_actor_outcome_and_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotation_id, line_id, candidate_id, product_id, decision_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    current_member = member()
    client = InsertClient({"id": decision_id})
    product = ProductSummary(
        id=product_id,
        tenant_name="Paper",
        canonical_name="Paper",
        base_unit="each",
        status="active",
    )
    decision = MatchDecision(
        id=decision_id,
        quotation_line_id=line_id,
        matched_product=product,
        selected_match_candidate_id=candidate_id,
        outcome="same_product",
        is_automatic=False,
        decided_by=current_member.membership_id,
        decided_at=datetime.now(UTC),
        confidence="0.8000",
    )
    recorded: list[tuple[object, str]] = []
    writer = SimpleNamespace(
        record=lambda event, bearer_token: recorded.append((event, bearer_token))
    )
    service = MatchResolutionService()
    service._aliases = SimpleNamespace(  # type: ignore[assignment] # test double
        learn_or_reuse_alias=lambda **_kwargs: uuid4()
    )
    service._landed_cost = SimpleNamespace(  # type: ignore[assignment] # test double
        compute_for_line_with_client=lambda **_kwargs: None
    )
    monkeypatch.setattr(resolution_module, "authenticated_client", lambda _settings, _token: client)
    monkeypatch.setattr(
        resolution_module,
        "_line_row",
        lambda _client, _id: {
            "id": line_id,
            "quotation_id": quotation_id,
            "original_text": "Paper",
        },
    )
    monkeypatch.setattr(resolution_module, "_decision_for_line", lambda _client, _id: None)
    monkeypatch.setattr(service, "_candidate_row", lambda *_args: {
        "id": candidate_id,
        "quotation_line_id": line_id,
        "candidate_workspace_product_id": product_id,
        "confidence": "0.8000",
    })
    monkeypatch.setattr(resolution_module, "_candidate", lambda *_args: None)
    monkeypatch.setattr(resolution_module, "_decision", lambda *_args: decision)
    monkeypatch.setattr(service, "_quotation_supplier_id", lambda *_args: None)
    monkeypatch.setattr(service, "_resolve_open_task", lambda *_args: None)
    monkeypatch.setattr(resolution_module, "get_audit_writer", lambda: writer)

    service.resolve(
        bearer_token="token",
        member=current_member,
        line_id=line_id,
        payload=MatchResolutionRequest(
            outcome="same_product", selected_match_candidate_id=candidate_id
        ),
    )

    event, token = recorded[0]
    assert token == "token"
    assert event.action == "matching.resolved"
    assert event.actor_membership_id == current_member.membership_id
    assert event.target["quotation_id"] == str(quotation_id)
    assert event.target["quotation_line_id"] == str(line_id)
    assert event.target["matched_product_id"] == str(product_id)
    assert event.target["outcome"] == "same_product"
