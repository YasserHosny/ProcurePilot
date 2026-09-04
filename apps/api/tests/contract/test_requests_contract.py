from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.requests.schemas import (
    ApprovalDecisionInput,
    ApprovalStep,
    Money,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestLine,
    PurchaseRequestList,
    PurchaseRequestUpdate,
)


def _line(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "workspace_product_id": uuid4(),
        "quantity": "10.000000",
    }
    base.update(overrides)
    return base


def _request(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "branch_id": uuid4(),
        "requested_by_membership_id": uuid4(),
        "required_by_date": "2026-09-15",
        "status": "draft",
        "lines": [_line()],
        "has_incomplete_estimate": False,
        "created_at": "2026-08-23T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_purchase_request_full_shape() -> None:
    pr = PurchaseRequest.model_validate(
        _request(
            cost_centre_id=uuid4(),
            estimated_total={"amount": "1500.0000", "currency": "GBP"},
            approval_step={
                "id": uuid4(),
                "assigned_membership_id": uuid4(),
                "source": "threshold_match",
                "status": "pending",
            },
            submitted_at="2026-08-23T10:00:00Z",
            updated_at="2026-08-23T10:00:00Z",
        )
    )
    assert pr.status == "draft"
    assert pr.estimated_total is not None
    assert pr.approval_step is not None
    assert pr.approval_step.status == "pending"


def test_purchase_request_minimal_shape() -> None:
    pr = PurchaseRequest.model_validate(_request())
    assert pr.cost_centre_id is None
    assert pr.estimated_total is None
    assert pr.approval_step is None
    assert pr.submitted_at is None
    assert pr.withdrawn_at is None
    assert pr.budget_status is None
    assert pr.updated_at is None


def test_purchase_request_list_with_cursor() -> None:
    lst = PurchaseRequestList(
        items=[PurchaseRequest.model_validate(_request())],
        next_cursor="abc",
    )
    assert len(lst.items) == 1
    assert lst.next_cursor == "abc"


def test_purchase_request_list_without_cursor() -> None:
    lst = PurchaseRequestList(items=[], next_cursor=None)
    assert lst.items == []
    assert lst.next_cursor is None


def test_purchase_request_line_with_estimate() -> None:
    line = PurchaseRequestLine.model_validate(
        _line(
            estimated_unit_price={"amount": "25.5000", "currency": "GBP"},
            estimated_unit_price_source_landed_cost_id=uuid4(),
        )
    )
    assert line.estimated_unit_price is not None
    assert line.estimated_unit_price.currency == "GBP"


def test_purchase_request_line_without_estimate() -> None:
    line = PurchaseRequestLine.model_validate(_line())
    assert line.estimated_unit_price is None
    assert line.estimated_unit_price_source_landed_cost_id is None


def test_create_requires_branch_date_and_lines() -> None:
    PurchaseRequestCreate(
        branch_id=uuid4(),
        required_by_date="2026-09-15",
        lines=[{"workspace_product_id": uuid4(), "quantity": "5.000000"}],
    )


def test_create_rejects_zero_lines() -> None:
    with pytest.raises(ValidationError, match="too_short"):
        PurchaseRequestCreate(
            branch_id=uuid4(),
            required_by_date="2026-09-15",
            lines=[],
        )


def test_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PurchaseRequestCreate.model_validate(
            {
                "branch_id": str(uuid4()),
                "required_by_date": "2026-09-15",
                "lines": [
                    {
                        "workspace_product_id": str(uuid4()),
                        "quantity": "1.000000",
                    }
                ],
                "status": "submitted",
            }
        )


def test_update_accepts_partial_patch() -> None:
    patch = PurchaseRequestUpdate(required_by_date="2026-10-01")
    assert "required_by_date" in patch.model_fields_set
    assert "branch_id" not in patch.model_fields_set
    assert "lines" not in patch.model_fields_set


def test_update_rejects_zero_lines_when_lines_provided() -> None:
    with pytest.raises(ValidationError, match="too_short"):
        PurchaseRequestUpdate(lines=[])


def test_update_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PurchaseRequestUpdate.model_validate({"status": "submitted"})


def test_approval_decision_input_optional_comment() -> None:
    with_comment = ApprovalDecisionInput(comment="Looks good")
    assert with_comment.comment == "Looks good"

    without = ApprovalDecisionInput()
    assert without.comment is None


def test_approval_decision_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ApprovalDecisionInput.model_validate({"status": "approved"})


def test_approval_step_decided_fields() -> None:
    step = ApprovalStep(
        id=uuid4(),
        assigned_membership_id=uuid4(),
        source="owner_fallback",
        status="approved",
        comment="LGTM",
        decided_by_membership_id=uuid4(),
        decided_at="2026-08-23T12:00:00Z",
    )
    assert step.decided_by_membership_id is not None
    assert step.decided_at is not None


def test_approval_step_pending_has_no_decision() -> None:
    step = ApprovalStep(
        id=uuid4(),
        assigned_membership_id=uuid4(),
        source="threshold_match",
        status="pending",
    )
    assert step.decided_by_membership_id is None
    assert step.decided_at is None


def test_money_rejects_invalid_patterns() -> None:
    with pytest.raises(ValidationError):
        Money(amount="abc", currency="GBP")
    with pytest.raises(ValidationError):
        Money(amount="10.0000", currency="gb")
    with pytest.raises(ValidationError):
        Money(amount="10.0000", currency="GBPP")


def test_all_status_values_are_valid() -> None:
    for s in ("draft", "submitted", "approved", "rejected", "withdrawn"):
        pr = PurchaseRequest.model_validate(_request(status=s))
        assert pr.status == s
