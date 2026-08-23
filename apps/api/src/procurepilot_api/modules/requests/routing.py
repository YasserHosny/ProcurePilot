from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from procurepilot_api.modules.requests.schemas import ApprovalStepSource


@dataclass(frozen=True)
class ThresholdRuleRow:
    id: UUID
    branch_id: UUID | None
    min_amount: Decimal
    max_amount: Decimal | None
    currency: str
    approver_membership_id: UUID


@dataclass(frozen=True)
class DelegationRow:
    id: UUID
    delegator_membership_id: UUID
    delegate_membership_id: UUID
    starts_on: date
    ends_on: date
    created_at: datetime


@dataclass(frozen=True)
class ResolvedApproval:
    assigned_membership_id: UUID
    source: ApprovalStepSource


def resolve_approver(
    *,
    request_value: Decimal | None,
    request_currency: str | None,
    branch_id: UUID,
    rules: Sequence[ThresholdRuleRow],
    delegations: Sequence[DelegationRow],
    removed_membership_ids: Collection[UUID],
    owner_membership_id: UUID,
    as_of: date,
) -> ResolvedApproval:
    """Resolve who a submitted request routes to (research.md R3). Pure function, no DB write —
    called once at submission time and its result is captured onto approval_step, never silently
    re-resolved afterward.

    Scope note: this only covers resolution AT SUBMISSION TIME. If an already-assigned approver
    is later removed from the workspace, that already-created approval_step is not re-resolved by
    this function — reassigning a pending step when its approver is removed is a separate concern
    that belongs in the member-removal flow (members/service.py), not here.
    """
    assignee, source = _resolve_threshold(
        request_value,
        request_currency,
        branch_id,
        rules,
        removed_membership_ids,
        owner_membership_id,
    )
    delegate = _active_delegation_for(assignee, delegations, as_of)
    if delegate is not None:
        return ResolvedApproval(assigned_membership_id=delegate, source="delegate")
    return ResolvedApproval(assigned_membership_id=assignee, source=source)


def _resolve_threshold(
    value: Decimal | None,
    currency: str | None,
    branch_id: UUID,
    rules: Sequence[ThresholdRuleRow],
    removed_membership_ids: Collection[UUID],
    owner_membership_id: UUID,
) -> tuple[UUID, ApprovalStepSource]:
    if value is None or currency is None:
        return owner_membership_id, "owner_fallback"

    matching = [
        rule
        for rule in rules
        if rule.currency == currency
        and rule.min_amount <= value
        and (rule.max_amount is None or value < rule.max_amount)
        and rule.approver_membership_id not in removed_membership_ids
    ]

    branch_specific = [rule for rule in matching if rule.branch_id == branch_id]
    tenant_wide = [rule for rule in matching if rule.branch_id is None]
    pool = branch_specific if branch_specific else tenant_wide

    if not pool:
        return owner_membership_id, "owner_fallback"

    def _range_width(rule: ThresholdRuleRow) -> Decimal:
        if rule.max_amount is None:
            return Decimal("Infinity")
        return rule.max_amount - rule.min_amount

    best = min(pool, key=_range_width)
    return best.approver_membership_id, "threshold_match"


def _active_delegation_for(
    membership_id: UUID,
    delegations: Sequence[DelegationRow],
    as_of: date,
) -> UUID | None:
    candidates = [
        delegation
        for delegation in delegations
        if delegation.delegator_membership_id == membership_id
        and delegation.starts_on <= as_of <= delegation.ends_on
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda delegation: (delegation.created_at, str(delegation.id)))
    return best.delegate_membership_id
