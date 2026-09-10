from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from procurepilot_api.main import create_app
from procurepilot_api.modules.requests.schemas import (
    ApprovalDecisionInput,
    ApprovalStep,
    BudgetStatus,
    PurchaseRequest,
    PurchaseRequestList,
)

# T022 [US2] — contract coverage for GET /approvals/pending and
# POST /requests/{id}/approve|/reject: the embedded-context shape (FR-005) and the
# 403/404/409 error envelopes. No DB — the RBAC gate and the state transitions are proven
# by the integration tests (T023); here we lock the wire shapes and route registration.


def _line(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "workspace_product_id": uuid4(),
        "quantity": "4.000000",
    }
    base.update(overrides)
    return base


def _queued_request(**overrides: object) -> dict:
    """A request as it appears in an approver's pending queue: every context field FR-005
    requires, embedded, plus the resolved (still-pending) approval step."""
    base = {
        "id": uuid4(),
        "branch_id": uuid4(),
        "cost_centre_id": uuid4(),
        "requested_by_membership_id": uuid4(),
        "required_by_date": "2026-09-20",
        "status": "submitted",
        "lines": [_line(), _line()],
        "estimated_total": {"amount": "820.0000", "currency": "GBP"},
        "has_incomplete_estimate": False,
        "budget_status": {
            "remaining_amount": {"amount": "500.0000", "currency": "GBP"},
            "exceeds": True,
        },
        "approval_step": {
            "id": uuid4(),
            "assigned_membership_id": uuid4(),
            "source": "threshold_match",
            "status": "pending",
        },
        "submitted_at": "2026-09-10T08:00:00Z",
        "created_at": "2026-09-10T07:55:00Z",
        "updated_at": "2026-09-10T08:00:00Z",
    }
    base.update(overrides)
    return base


def test_pending_queue_row_carries_every_fr005_context_field() -> None:
    pr = PurchaseRequest.model_validate(_queued_request())

    assert pr.requested_by_membership_id is not None
    assert pr.branch_id is not None
    assert pr.cost_centre_id is not None
    assert pr.required_by_date.isoformat() == "2026-09-20"
    assert len(pr.lines) == 2
    assert pr.approval_step is not None
    assert pr.approval_step.status == "pending"
    assert pr.approval_step.decided_by_membership_id is None
    assert pr.budget_status is not None
    assert pr.budget_status.exceeds is True


def test_pending_queue_is_a_purchase_request_list() -> None:
    queue = PurchaseRequestList(
        items=[PurchaseRequest.model_validate(_queued_request())],
        next_cursor="eyJvZmZzZXQiOjI1fQ==",
    )
    assert len(queue.items) == 1
    assert queue.next_cursor is not None

    empty = PurchaseRequestList(items=[], next_cursor=None)
    assert empty.items == []
    assert empty.next_cursor is None


def test_budget_status_is_optional_and_omitted_when_no_budget_applies() -> None:
    pr = PurchaseRequest.model_validate(
        _queued_request(budget_status=None)
    )
    assert pr.budget_status is None


def test_budget_status_shape_is_money_plus_exceeds() -> None:
    status = BudgetStatus.model_validate(
        {
            "remaining_amount": {"amount": "125.5000", "currency": "GBP"},
            "exceeds": False,
        }
    )
    assert status.remaining_amount.currency == "GBP"
    assert status.exceeds is False

    with pytest.raises(ValidationError):
        BudgetStatus.model_validate(
            {"remaining_amount": {"amount": "10", "currency": "gbp"}, "exceeds": True}
        )


def test_decided_step_populates_decided_by_and_decided_at_together() -> None:
    approved = PurchaseRequest.model_validate(
        _queued_request(
            status="approved",
            approval_step={
                "id": uuid4(),
                "assigned_membership_id": uuid4(),
                "source": "owner_fallback",
                "status": "approved",
                "comment": "Within the branch quarterly budget",
                "decided_by_membership_id": uuid4(),
                "decided_at": "2026-09-11T09:30:00Z",
            },
        )
    )
    step = approved.approval_step
    assert step is not None
    assert step.status == "approved"
    assert step.decided_by_membership_id is not None
    assert step.decided_at is not None
    assert step.comment == "Within the branch quarterly budget"


def test_owner_override_decider_differs_from_assignee_is_representable() -> None:
    # FR-007: an owner may decide a step assigned to someone else.
    assignee = uuid4()
    owner = uuid4()
    step = ApprovalStep(
        id=uuid4(),
        assigned_membership_id=assignee,
        source="threshold_match",
        status="rejected",
        decided_by_membership_id=owner,
        decided_at="2026-09-11T10:00:00Z",
    )
    assert step.decided_by_membership_id != step.assigned_membership_id


def test_approve_reject_body_is_optional_comment_only() -> None:
    assert ApprovalDecisionInput().comment is None
    assert ApprovalDecisionInput(comment="ok").comment == "ok"
    with pytest.raises(ValidationError):
        ApprovalDecisionInput.model_validate({"status": "approved"})


def test_decision_error_envelopes_map_to_the_documented_status_codes() -> None:
    assert PermissionDeniedError().status_code == 403
    assert PermissionDeniedError().code == "auth.permission_denied"
    assert NotFoundError().status_code == 404
    assert ConflictError().status_code == 409

    # The reasons the approve/reject path attaches, surfaced in the envelope's `details`.
    assert PermissionDeniedError(
        details={"reason": "not_assigned_approver"}
    ).details == {"reason": "not_assigned_approver"}
    for reason in ("not_submitted", "no_pending_approval"):
        assert ConflictError(details={"reason": reason}).details == {"reason": reason}


def test_approval_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}
    for path in (
        "/api/v1/approvals/pending",
        "/api/v1/requests/{request_id}/approve",
        "/api/v1/requests/{request_id}/reject",
    ):
        assert path in app_paths, f"{path} not registered in the app"


def test_contract_declares_the_approval_paths() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    text = (
        repo_root
        / "specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml"
    ).read_text(encoding="utf-8")
    for path in (
        "/approvals/pending",
        "/requests/{request_id}/approve",
        "/requests/{request_id}/reject",
    ):
        assert f"  {path}:" in text, f"{path} missing from the contract"
