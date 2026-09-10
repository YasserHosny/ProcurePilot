from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.errors import (
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from procurepilot_api.main import create_app
from procurepilot_api.modules.requests.schemas import (
    ApprovalDelegation,
    ApprovalDelegationCreate,
    ApprovalDelegationList,
    ThresholdRule,
    ThresholdRuleCreate,
    ThresholdRuleList,
    ThresholdRuleUpdate,
)

# T030 [US3] — contract coverage for the threshold-rule and delegation endpoints:
# GET/POST /approvals/threshold-rules, PATCH/DELETE /approvals/threshold-rules/{id},
# GET/POST /approvals/delegations, DELETE /approvals/delegations/{id}. Owner-only writes and
# the 403/404/422 envelopes. No DB — the RBAC gate is a service-layer check proven by
# integration tests; here we lock the wire shapes and route registration.


def _rule(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "min_amount": "0.0000",
        "max_amount": "5000.0000",
        "currency": "GBP",
        "approver_membership_id": uuid4(),
        "created_by": uuid4(),
        "created_at": "2026-09-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _delegation(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "delegator_membership_id": uuid4(),
        "delegate_membership_id": uuid4(),
        "starts_on": "2026-09-01",
        "ends_on": "2026-09-30",
        "created_at": "2026-08-25T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_threshold_rule_full_shape() -> None:
    rule = ThresholdRule.model_validate(
        _rule(branch_id=uuid4(), updated_at="2026-09-05T00:00:00Z")
    )
    assert rule.branch_id is not None
    assert rule.max_amount == "5000.0000"
    assert rule.updated_at is not None


def test_threshold_rule_tenant_wide_and_top_tier_are_nullable() -> None:
    rule = ThresholdRule.model_validate(_rule(branch_id=None, max_amount=None))
    assert rule.branch_id is None  # null branch_id = tenant-wide default rule
    assert rule.max_amount is None  # null max_amount = top tier, no ceiling
    assert rule.updated_at is None


def test_threshold_rule_amount_and_currency_patterns_are_enforced() -> None:
    with pytest.raises(ValidationError):
        ThresholdRule.model_validate(_rule(min_amount="abc"))
    with pytest.raises(ValidationError):
        ThresholdRule.model_validate(_rule(min_amount="1.234567"))
    with pytest.raises(ValidationError):
        ThresholdRule.model_validate(_rule(currency="gbp"))


def test_threshold_rule_create_requires_bounds_currency_and_approver() -> None:
    created = ThresholdRuleCreate(
        min_amount="0.0000",
        currency="GBP",
        approver_membership_id=uuid4(),
    )
    assert created.branch_id is None
    assert created.max_amount is None

    with pytest.raises(ValidationError):
        ThresholdRuleCreate(currency="GBP", approver_membership_id=uuid4())


def test_threshold_rule_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ThresholdRuleCreate.model_validate(
            {
                "min_amount": "0.0000",
                "currency": "GBP",
                "approver_membership_id": str(uuid4()),
                "created_by": str(uuid4()),
            }
        )


def test_threshold_rule_update_is_an_all_optional_partial_patch() -> None:
    patch = ThresholdRuleUpdate(max_amount="9999.0000")
    assert "max_amount" in patch.model_fields_set
    assert "min_amount" not in patch.model_fields_set
    assert "approver_membership_id" not in patch.model_fields_set

    with pytest.raises(ValidationError):
        ThresholdRuleUpdate.model_validate({"id": str(uuid4())})


def test_threshold_rule_list_with_and_without_cursor() -> None:
    listed = ThresholdRuleList(
        items=[ThresholdRule.model_validate(_rule())], next_cursor="abc"
    )
    assert len(listed.items) == 1
    assert listed.next_cursor == "abc"
    assert ThresholdRuleList(items=[]).next_cursor is None


def test_delegation_full_shape() -> None:
    delegation = ApprovalDelegation.model_validate(_delegation())
    assert delegation.delegator_membership_id != delegation.delegate_membership_id
    assert delegation.starts_on.isoformat() == "2026-09-01"
    assert delegation.ends_on.isoformat() == "2026-09-30"


def test_delegation_create_defaults_delegator_to_the_caller() -> None:
    created = ApprovalDelegationCreate(
        delegate_membership_id=uuid4(),
        starts_on="2026-09-01",
        ends_on="2026-09-30",
    )
    assert created.delegator_membership_id is None  # server fills in the caller

    explicit = ApprovalDelegationCreate(
        delegator_membership_id=uuid4(),
        delegate_membership_id=uuid4(),
        starts_on="2026-09-01",
        ends_on="2026-09-30",
    )
    assert explicit.delegator_membership_id is not None


def test_delegation_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ApprovalDelegationCreate.model_validate(
            {
                "delegate_membership_id": str(uuid4()),
                "starts_on": "2026-09-01",
                "ends_on": "2026-09-30",
                "id": str(uuid4()),
            }
        )


def test_delegation_list_shape() -> None:
    listed = ApprovalDelegationList(
        items=[ApprovalDelegation.model_validate(_delegation())]
    )
    assert len(listed.items) == 1


def test_owner_only_and_validation_error_envelopes_map_to_status_codes() -> None:
    assert PermissionDeniedError().status_code == 403
    assert NotFoundError().status_code == 404
    assert UnprocessableEntityError().status_code == 422
    assert UnprocessableEntityError().code == "validation.invalid_value"

    # Reasons the threshold-rule / delegation write paths attach.
    assert PermissionDeniedError(details={"reason": "owner_required"}).details == {
        "reason": "owner_required"
    }
    assert PermissionDeniedError(
        details={"reason": "not_delegator_or_owner"}
    ).details == {"reason": "not_delegator_or_owner"}


def test_threshold_rule_and_delegation_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}
    for path in (
        "/api/v1/approvals/threshold-rules",
        "/api/v1/approvals/threshold-rules/{rule_id}",
        "/api/v1/approvals/delegations",
        "/api/v1/approvals/delegations/{delegation_id}",
    ):
        assert path in app_paths, f"{path} not registered in the app"


def test_contract_declares_the_threshold_rule_and_delegation_paths() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    text = (
        repo_root
        / "specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml"
    ).read_text(encoding="utf-8")
    for path in (
        "/approvals/threshold-rules",
        "/approvals/threshold-rules/{rule_id}",
        "/approvals/delegations",
        "/approvals/delegations/{delegation_id}",
    ):
        assert f"  {path}:" in text, f"{path} missing from the contract"
