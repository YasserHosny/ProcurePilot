from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching import resolution_service as resolution_module
from procurepilot_api.modules.matching import router as matching_router
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
    monkeypatch.setattr(
        service,
        "_candidate_row",
        lambda *_args: {
            "id": candidate_id,
            "quotation_line_id": line_id,
            "candidate_workspace_product_id": product_id,
            "confidence": "0.8000",
        },
    )
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


def test_match_resolution_route_passes_idempotency_key_to_service() -> None:
    line_id, candidate_id, idempotency_key = uuid4(), uuid4(), uuid4()
    payload = MatchResolutionRequest(
        outcome="same_product",
        selected_match_candidate_id=candidate_id,
    )
    captured: dict[str, object] = {}
    expected = object()
    service = SimpleNamespace(resolve=lambda **kwargs: captured.update(kwargs) or expected)

    result = matching_router.resolve_match(
        line_id=line_id,
        payload=payload,
        token="token",
        member=member(),
        service=service,
        _idempotency_key=idempotency_key,
    )

    assert result is expected
    assert captured["idempotency_key"] == idempotency_key


def test_human_resolution_replays_previous_decision_for_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id, candidate_id, decision_id, product_id, idempotency_key = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    current_member = member()
    decision = MatchDecision(
        id=decision_id,
        quotation_line_id=line_id,
        matched_product=ProductSummary(
            id=product_id,
            tenant_name="Paper",
            canonical_name="Paper",
            base_unit="each",
            status="active",
        ),
        selected_match_candidate_id=candidate_id,
        outcome="same_product",
        is_automatic=False,
        decided_by=current_member.membership_id,
        decided_at=datetime.now(UTC),
        confidence="0.8000",
    )
    payload = MatchResolutionRequest(
        outcome="same_product",
        selected_match_candidate_id=candidate_id,
    )
    monkeypatch.setattr(
        resolution_module,
        "authenticated_client",
        lambda _settings, _token: object(),
    )
    monkeypatch.setattr(resolution_module, "_line_row", lambda _client, _id: {})
    monkeypatch.setattr(
        resolution_module,
        "_idempotency_record_for_key",
        lambda _client, _tenant_id, _key: {
            "idempotency_key": idempotency_key,
            "quotation_line_id": line_id,
            "request_fingerprint": resolution_module._request_fingerprint(payload),
            "match_decision_id": decision_id,
        },
        raising=False,
    )
    monkeypatch.setattr(
        resolution_module,
        "_decision_by_id",
        lambda _client, _decision_id: {"id": decision_id},
        raising=False,
    )
    monkeypatch.setattr(resolution_module, "_decision", lambda *_args: decision)

    result = MatchResolutionService().resolve(
        bearer_token="token",
        member=current_member,
        line_id=line_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )

    assert result is decision


def test_human_resolution_rejects_reused_idempotency_key_for_different_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id, candidate_id, idempotency_key = uuid4(), uuid4(), uuid4()
    current_member = member()
    payload = MatchResolutionRequest(
        outcome="same_product",
        selected_match_candidate_id=candidate_id,
    )
    monkeypatch.setattr(
        resolution_module,
        "authenticated_client",
        lambda _settings, _token: object(),
    )
    monkeypatch.setattr(resolution_module, "_line_row", lambda _client, _id: {})
    monkeypatch.setattr(
        resolution_module,
        "_idempotency_record_for_key",
        lambda _client, _tenant_id, _key: {
            "idempotency_key": idempotency_key,
            "quotation_line_id": line_id,
            "request_fingerprint": "different",
            "match_decision_id": uuid4(),
        },
        raising=False,
    )

    with pytest.raises(resolution_module.ConflictError) as exc_info:
        MatchResolutionService().resolve(
            bearer_token="token",
            member=current_member,
            line_id=line_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    assert exc_info.value.details == {"reason": "idempotency_key_reused"}


def test_human_resolution_retry_repairs_missing_side_effects_after_decision_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id, candidate_id, decision_id, product_id, idempotency_key = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    current_member = member()
    payload = MatchResolutionRequest(
        outcome="same_product",
        selected_match_candidate_id=candidate_id,
    )
    decision_row = {
        "id": decision_id,
        "quotation_line_id": line_id,
        "matched_workspace_product_id": product_id,
        "selected_match_candidate_id": candidate_id,
        "outcome": "same_product",
        "is_automatic": False,
        "decided_by": current_member.membership_id,
        "decided_at": datetime.now(UTC),
        "confidence": "0.8000",
        "alias_id": None,
    }
    decision = MatchDecision(
        id=decision_id,
        quotation_line_id=line_id,
        matched_product=ProductSummary(
            id=product_id,
            tenant_name="Paper",
            canonical_name="Paper",
            base_unit="each",
            status="active",
        ),
        selected_match_candidate_id=candidate_id,
        outcome="same_product",
        is_automatic=False,
        decided_by=current_member.membership_id,
        decided_at=decision_row["decided_at"],
        confidence="0.8000",
    )
    side_effects: list[str] = []
    service = MatchResolutionService()
    service._landed_cost = SimpleNamespace(  # type: ignore[assignment] # test double
        compute_for_line_with_client=lambda **_kwargs: side_effects.append("landed_cost")
    )
    monkeypatch.setattr(
        resolution_module, "authenticated_client", lambda _settings, _token: object()
    )
    monkeypatch.setattr(
        resolution_module,
        "_idempotency_record_for_key",
        lambda _client, _tenant_id, _key: None,
    )
    monkeypatch.setattr(
        resolution_module,
        "_line_row",
        lambda _client, _id: {
            "id": line_id,
            "quotation_id": uuid4(),
            "original_text": "Paper",
        },
    )
    monkeypatch.setattr(resolution_module, "_decision_for_line", lambda _client, _id: decision_row)
    monkeypatch.setattr(resolution_module, "_decision", lambda *_args: decision)
    monkeypatch.setattr(service, "_resolve_open_task", lambda *_args: side_effects.append("task"))
    monkeypatch.setattr(
        resolution_module,
        "_matching_resolution_audit_exists",
        lambda *_args: False,
        raising=False,
    )
    monkeypatch.setattr(
        resolution_module,
        "_record_idempotency_decision",
        lambda **_kwargs: side_effects.append("idempotency"),
    )
    writer = SimpleNamespace(record=lambda *_args, **_kwargs: side_effects.append("audit"))
    monkeypatch.setattr(resolution_module, "get_audit_writer", lambda: writer)

    result = service.resolve(
        bearer_token="token",
        member=current_member,
        line_id=line_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )

    assert result is decision
    assert side_effects == ["task", "audit", "landed_cost", "idempotency"]


def test_human_resolution_retry_rejects_different_payload_after_decision_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id, existing_candidate_id, requested_candidate_id, idempotency_key = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    current_member = member()
    side_effects: list[str] = []
    service = MatchResolutionService()
    monkeypatch.setattr(
        resolution_module, "authenticated_client", lambda _settings, _token: object()
    )
    monkeypatch.setattr(
        resolution_module,
        "_idempotency_record_for_key",
        lambda _client, _tenant_id, _key: None,
    )
    monkeypatch.setattr(
        resolution_module,
        "_line_row",
        lambda _client, _id: {
            "id": line_id,
            "quotation_id": uuid4(),
            "original_text": "Paper",
        },
    )
    monkeypatch.setattr(
        resolution_module,
        "_decision_for_line",
        lambda _client, _id: {
            "quotation_line_id": line_id,
            "selected_match_candidate_id": existing_candidate_id,
            "outcome": "same_product",
        },
    )
    monkeypatch.setattr(service, "_resolve_open_task", lambda *_args: side_effects.append("task"))

    with pytest.raises(resolution_module.ConflictError) as exc_info:
        service.resolve(
            bearer_token="token",
            member=current_member,
            line_id=line_id,
            payload=MatchResolutionRequest(
                outcome="same_product",
                selected_match_candidate_id=requested_candidate_id,
            ),
            idempotency_key=idempotency_key,
        )

    assert exc_info.value.details == {"reason": "line_already_matched"}
    assert side_effects == []
