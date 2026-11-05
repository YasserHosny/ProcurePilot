"""Bulk decisions delegate to the single path, retaining order and item isolation."""

from __future__ import annotations

from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError
from unit.test_approval_decisions import member, request_row, step_row
from unit.test_request_self_approval import DecisionCursor

from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as module
from procurepilot_api.modules.requests.schemas import BulkApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService, _purchase_request


@pytest.mark.parametrize(
    "changes",
    [
        {"request_ids": []},
        {"request_ids": [str(uuid4()) for _ in range(26)]},
        {"request_ids": ["11111111-1111-4111-8111-111111111111"] * 2},
        {"request_ids": ["invalid"]},
        {"decision": "pending"},
        {"decision": "rejected"},
        {"decision": "rejected", "comment": " \t\n"},
        {"comment": "x" * 2001},
        {"tenant_id": str(uuid4())},
    ],
)
def test_invalid_batch_is_rejected_before_service(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BulkApprovalDecisionInput.model_validate(
            {"decision": "approved", "request_ids": [str(uuid4())], **changes}
        )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_batch_limits_and_comment_boundary(decision: str) -> None:
    body = BulkApprovalDecisionInput.model_validate(
        {"decision": decision, "comment": "x" * 2000, "request_ids": [uuid4() for _ in range(25)]}
    )
    assert len(body.request_ids) == 25


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_failures_are_isolated_in_body_order_and_keys_are_derived(
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
) -> None:
    service, actor, key = RequestsService(), member(), uuid4()
    ids = [uuid4() for _ in range(9)]
    failures = [
        None,
        ConflictError(details={"reason": "not_submitted"}),
        NotFoundError(),
        PermissionDeniedError(details={"reason": "self_decision_not_allowed"}),
        ConflictError(details={"reason": "part_of_split", "request_group_id": str(uuid4())}),
        ServiceUnavailableError(),
        RuntimeError("private infrastructure details"),
        PermissionDeniedError(details={"reason": "not_assigned_approver"}),
        None,
    ]
    calls: list[dict[str, object]] = []

    def decide(**kwargs: object) -> object:
        calls.append(kwargs)
        index = ids.index(kwargs["request_id"])
        if failures[index] is not None:
            raise failures[index]
        row = request_row(ids[index], uuid4(), status=decision)
        row["estimated_total_currency"] = "GBP" if index == 0 else "EGP"
        return _purchase_request(row, [], None)

    monkeypatch.setattr(service, "_decide_request", decide)
    result = service.bulk_decisions(
        bearer_token="token",
        member=actor,
        idempotency_key=key,
        payload=BulkApprovalDecisionInput(decision=decision, comment="Reason", request_ids=ids),
    )
    assert [item.request_id for item in result.results] == ids
    assert [item.error_code for item in result.results] == [
        None,
        "conflict",
        "not_found",
        "self_decision_not_allowed",
        "group_request_use_group_decision",
        "unavailable",
        "unavailable",
        "auth.permission_denied",
        None,
    ]
    assert [item.outcome for item in result.results] == ["decided"] + ["failed"] * 7 + ["decided"]
    assert result.decided_count == 2
    assert result.failed_count == 7
    assert all(item.request is None for item in result.results[1:-1])
    assert [call["idempotency_key"] for call in calls] == [uuid5(key, str(rid)) for rid in ids]
    assert all(call["bearer_token"] == "token" and call["member"] is actor for call in calls)
    assert all(
        call["decision"] == decision and call["payload"].comment == "Reason" for call in calls
    )
    assert result.results[0].request.estimated_total.currency == "GBP"
    assert result.results[-1].request.estimated_total.currency == "EGP"
    assert "private infrastructure details" not in result.model_dump_json()


def test_replay_reuses_item_keys_instead_of_recording_another_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, actor = RequestsService(), member()
    ids, key = [uuid4(), uuid4()], uuid4()
    recorded: dict[UUID, object] = {}
    calls: list[UUID] = []

    def decide(**kwargs: object) -> object:
        item_key = kwargs["idempotency_key"]
        calls.append(item_key)
        if item_key not in recorded:
            recorded[item_key] = _purchase_request(
                request_row(kwargs["request_id"], uuid4(), status="approved"), [], None
            )
        return recorded[item_key]

    monkeypatch.setattr(service, "_decide_request", decide)
    payload = BulkApprovalDecisionInput(decision="approved", request_ids=ids)
    first = service.bulk_decisions(
        bearer_token="t", member=actor, payload=payload, idempotency_key=key
    )
    second = service.bulk_decisions(
        bearer_token="t", member=actor, payload=payload, idempotency_key=key
    )
    assert first == second
    assert len(recorded) == 2
    assert calls == [uuid5(key, str(rid)) for rid in ids] * 2


def test_group_failure_comes_from_the_single_path(monkeypatch: pytest.MonkeyPatch) -> None:
    service, actor, rid = RequestsService(), member(), uuid4()
    row = {**request_row(rid, uuid4()), "request_group_id": uuid4()}
    monkeypatch.setattr(module, "authenticated_client", lambda *_: object())
    monkeypatch.setattr(service, "_fetch_request", lambda *_: row)
    result = service.bulk_decisions(
        bearer_token="t",
        member=actor,
        idempotency_key=uuid4(),
        payload=BulkApprovalDecisionInput(decision="approved", request_ids=[rid]),
    )
    assert result.results[0].error_code == "group_request_use_group_decision"


def test_bulk_uses_the_single_path_self_decision_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, actor = RequestsService(), member(role=MemberRole.owner)
    rid = uuid4()
    row, step = request_row(rid, actor.membership_id), step_row(rid, actor.membership_id)
    cursor = DecisionCursor(row, step, [actor.membership_id, uuid4()])
    monkeypatch.setattr(module, "authenticated_client", lambda *_: object())
    monkeypatch.setattr(service, "_fetch_request", lambda *_: row)
    monkeypatch.setattr(service, "_fetch_lines_for", lambda *_: [])
    monkeypatch.setattr(
        service, "_purchase_request_with_budget_status", lambda *_: _purchase_request(row, [], step)
    )

    def transaction(**kwargs: object) -> tuple[dict, dict, None]:
        request, approval = service._apply_request_decision(
            cursor,
            member=actor,
            request_id=str(rid),
            step_id=str(step["id"]),
            decision=kwargs["decision"],
            request_status=kwargs["decision"],
            comment=kwargs["comment"],
            now=kwargs["now"],
        )
        return request, approval, None

    monkeypatch.setattr(service, "_decide_and_notify", transaction)
    result = service.bulk_decisions(
        bearer_token="t",
        member=actor,
        idempotency_key=uuid4(),
        payload=BulkApprovalDecisionInput(decision="approved", request_ids=[rid]),
    )
    assert result.failed_count == 1
    assert result.results[0].error_code == "self_decision_not_allowed"
    assert cursor.writes == []
