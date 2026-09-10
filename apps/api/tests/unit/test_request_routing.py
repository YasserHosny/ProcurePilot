from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from procurepilot_api.modules.requests.routing import (
    DelegationRow,
    ThresholdRuleRow,
    resolve_approver,
)


def rule(
    *,
    branch_id: UUID | None = None,
    minimum: str = "0",
    maximum: str | None = None,
    currency: str = "GBP",
    approver_id: UUID | None = None,
) -> ThresholdRuleRow:
    return ThresholdRuleRow(
        id=uuid4(),
        branch_id=branch_id,
        min_amount=Decimal(minimum),
        max_amount=Decimal(maximum) if maximum is not None else None,
        currency=currency,
        approver_membership_id=approver_id or uuid4(),
    )


def delegation(
    *,
    delegator_id: UUID,
    delegate_id: UUID,
    starts_on: date = date(2026, 9, 1),
    ends_on: date = date(2026, 9, 30),
) -> DelegationRow:
    return DelegationRow(
        id=uuid4(),
        delegator_membership_id=delegator_id,
        delegate_membership_id=delegate_id,
        starts_on=starts_on,
        ends_on=ends_on,
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )


def test_branch_specific_rule_wins_over_tenant_default() -> None:
    branch_id = uuid4()
    owner_id = uuid4()
    default_approver = uuid4()
    branch_approver = uuid4()

    result = resolve_approver(
        request_value=Decimal("250"),
        request_currency="GBP",
        branch_id=branch_id,
        rules=[
            rule(approver_id=default_approver),
            rule(branch_id=branch_id, approver_id=branch_approver),
        ],
        delegations=[],
        removed_membership_ids=set(),
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == branch_approver
    assert result.source == "threshold_match"


def test_narrowest_matching_range_wins_when_rules_overlap() -> None:
    branch_id = uuid4()
    owner_id = uuid4()
    broad_approver = uuid4()
    narrow_approver = uuid4()

    result = resolve_approver(
        request_value=Decimal("75"),
        request_currency="GBP",
        branch_id=branch_id,
        rules=[
            rule(minimum="0", maximum="1000", approver_id=broad_approver),
            rule(minimum="50", maximum="100", approver_id=narrow_approver),
        ],
        delegations=[],
        removed_membership_ids=set(),
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == narrow_approver
    assert result.source == "threshold_match"


def test_active_delegation_redirects_threshold_resolved_assignee() -> None:
    branch_id = uuid4()
    owner_id = uuid4()
    approver = uuid4()
    delegate = uuid4()

    result = resolve_approver(
        request_value=Decimal("75"),
        request_currency="GBP",
        branch_id=branch_id,
        rules=[rule(approver_id=approver)],
        delegations=[delegation(delegator_id=approver, delegate_id=delegate)],
        removed_membership_ids=set(),
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == delegate
    assert result.source == "delegate"


def test_owner_fallback_when_no_rule_matches_or_estimate_is_incomplete() -> None:
    branch_id = uuid4()
    owner_id = uuid4()

    result = resolve_approver(
        request_value=None,
        request_currency=None,
        branch_id=branch_id,
        rules=[rule(currency="USD")],
        delegations=[],
        removed_membership_ids=set(),
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == owner_id
    assert result.source == "owner_fallback"


def test_removed_threshold_approver_falls_back_to_owner() -> None:
    branch_id = uuid4()
    owner_id = uuid4()
    removed_approver = uuid4()

    result = resolve_approver(
        request_value=Decimal("75"),
        request_currency="GBP",
        branch_id=branch_id,
        rules=[rule(approver_id=removed_approver)],
        delegations=[],
        removed_membership_ids={removed_approver},
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == owner_id
    assert result.source == "owner_fallback"


def test_delegation_to_removed_delegate_falls_through_to_original_assignee() -> None:
    branch_id = uuid4()
    owner_id = uuid4()
    approver = uuid4()
    removed_delegate = uuid4()

    result = resolve_approver(
        request_value=Decimal("75"),
        request_currency="GBP",
        branch_id=branch_id,
        rules=[rule(approver_id=approver)],
        delegations=[delegation(delegator_id=approver, delegate_id=removed_delegate)],
        removed_membership_ids={removed_delegate},
        owner_membership_id=owner_id,
        as_of=date(2026, 9, 10),
    )

    assert result.assigned_membership_id == approver
    assert result.source == "threshold_match"
