"""Request routing integration coverage — task T031.

The pure resolver is already covered in unit tests. These checks exercise the submit path that
uses it: request estimates are frozen, an approval step is created for the resolved assignee, and
the pending queue returns the same routed step. Owner fallback also has to emit the escalation
audit event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.routing import DelegationRow, ThresholdRuleRow
from procurepilot_api.modules.requests.schemas import ApprovalStepSource
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.requests.valuation import LineEstimate
from procurepilot_api.shared.audit import AuditEventCreate


@dataclass
class Response:
    data: list[dict[str, object]]


class FakeQuery:
    def __init__(self, client: FakeClient, table: str) -> None:
        self.client = client
        self.table = table
        self.insert_body: dict[str, object] | None = None
        self.update_body: dict[str, object] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def insert(self, body: dict[str, object]) -> FakeQuery:
        self.insert_body = body
        return self

    def update(self, body: dict[str, object]) -> FakeQuery:
        self.update_body = body
        return self

    def eq(self, _column: str, _value: object) -> FakeQuery:
        return self

    def in_(self, _column: str, _value: object) -> FakeQuery:
        return self

    def order(self, _column: str, *, desc: bool = False) -> FakeQuery:
        return self

    def range(self, _start: int, _end: int) -> FakeQuery:
        return self

    def limit(self, _count: int) -> FakeQuery:
        return self

    def execute(self) -> Response:
        if self.insert_body is not None:
            if self.table != "approval_step":
                raise AssertionError(f"unexpected insert into {self.table}")
            row = {
                "id": str(uuid4()),
                "comment": None,
                "decided_by_membership_id": None,
                "decided_at": None,
                **self.insert_body,
            }
            self.client.step_rows.append(row)
            return Response([row])

        if self.update_body is not None:
            if self.table == "purchase_request":
                self.client.request_row.update(self.update_body)
                return Response([self.client.request_row])
            if self.table == "purchase_request_line":
                self.client.line_row.update(self.update_body)
                return Response([self.client.line_row])
            raise AssertionError(f"unexpected update of {self.table}")

        if self.table == "approval_step":
            return Response(self.client.step_rows)
        return Response([])


class FakeClient:
    def __init__(
        self,
        request_row: dict[str, object],
        line_row: dict[str, object],
    ) -> None:
        self.request_row = request_row
        self.line_row = line_row
        self.step_rows: list[dict[str, object]] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


class FakeAuditWriter:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def record(self, event: AuditEventCreate, *, bearer_token: str) -> None:
        self.actions.append(str(event.action))


def request_row(
    *,
    request_id: UUID,
    tenant_id: UUID,
    branch_id: UUID,
    requester_id: UUID,
) -> dict[str, object]:
    return {
        "id": str(request_id),
        "tenant_id": str(tenant_id),
        "branch_id": str(branch_id),
        "cost_centre_id": None,
        "requested_by_membership_id": str(requester_id),
        "required_by_date": "2026-09-15",
        "status": "draft",
        "estimated_total_amount": None,
        "estimated_total_currency": None,
        "has_incomplete_estimate": False,
        "submitted_at": None,
        "withdrawn_at": None,
        "created_at": "2026-09-11T08:55:00Z",
        "updated_at": None,
    }


def line_row(*, request_id: UUID, product_id: UUID) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "purchase_request_id": str(request_id),
        "workspace_product_id": str(product_id),
        "quantity": "5.000000",
        "note": None,
        "estimated_unit_price_amount": None,
        "estimated_unit_price_currency": None,
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": None,
    }


def owner_member(
    *,
    tenant_id: UUID,
    membership_id: UUID,
) -> CurrentMember:
    return CurrentMember(
        tenant_id=tenant_id,
        membership_id=membership_id,
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )


def threshold_rule(
    *,
    branch_id: UUID | None,
    min_amount: str,
    max_amount: str | None,
    approver_id: UUID,
) -> ThresholdRuleRow:
    return ThresholdRuleRow(
        id=uuid4(),
        branch_id=branch_id,
        min_amount=Decimal(min_amount),
        max_amount=Decimal(max_amount) if max_amount is not None else None,
        currency="GBP",
        approver_membership_id=approver_id,
    )


def active_delegation(*, delegator_id: UUID, delegate_id: UUID) -> DelegationRow:
    return DelegationRow(
        id=uuid4(),
        delegator_membership_id=delegator_id,
        delegate_membership_id=delegate_id,
        starts_on=date.today() - timedelta(days=1),
        ends_on=date.today() + timedelta(days=1),
        created_at=datetime.now(UTC),
    )


def build_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rules: list[ThresholdRuleRow],
    delegations: list[DelegationRow] | None = None,
    removed_membership_ids: set[UUID] | None = None,
) -> tuple[RequestsService, FakeClient, CurrentMember, UUID]:
    tenant_id = uuid4()
    branch_id = uuid4()
    owner_id = uuid4()
    request_id = uuid4()
    product_id = uuid4()
    req = request_row(
        request_id=request_id,
        tenant_id=tenant_id,
        branch_id=branch_id,
        requester_id=owner_id,
    )
    line = line_row(request_id=request_id, product_id=product_id)
    client = FakeClient(req, line)
    service = RequestsService()
    member = owner_member(tenant_id=tenant_id, membership_id=owner_id)

    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.authenticated_client",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(service, "_fetch_request", lambda _client, _id: req)
    monkeypatch.setattr(service, "_fetch_lines_for", lambda _client, _id: [line])
    monkeypatch.setattr(
        service,
        "_estimate_products",
        lambda _ids: [LineEstimate(Decimal("60.0000"), "GBP", None)],
    )
    monkeypatch.setattr(service, "_fetch_threshold_rules", lambda _client: rules)
    monkeypatch.setattr(
        service,
        "_fetch_active_delegations",
        lambda _client, *, as_of: delegations or [],
    )
    monkeypatch.setattr(
        service,
        "_fetch_removed_membership_ids",
        lambda _client: removed_membership_ids or set(),
    )
    monkeypatch.setattr(service, "_fetch_owner_membership_id", lambda _client: owner_id)
    monkeypatch.setattr(service, "_fetch_requests_batch", lambda _client, _ids: [req])
    monkeypatch.setattr(
        service,
        "_fetch_lines_batch",
        lambda _client, _ids: {str(request_id): [line]},
    )
    monkeypatch.setattr(service, "_fetch_budget_rows", lambda _client: [])
    monkeypatch.setattr(service, "_fetch_committed_spend_rows", lambda _client: [])
    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.get_audit_writer",
        lambda: FakeAuditWriter(),
    )

    return service, client, member, request_id


def submit_and_fetch_pending(
    service: RequestsService,
    member: CurrentMember,
    request_id: UUID,
) -> tuple[ApprovalStepSource, UUID]:
    submitted = service.submit_request(
        bearer_token="token",
        member=member,
        request_id=request_id,
    )
    pending = service.list_pending_approvals(
        bearer_token="token",
        member=member,
    )

    assert submitted.approval_step is not None
    assert pending.items[0].approval_step is not None
    assert pending.items[0].approval_step.id == submitted.approval_step.id
    return submitted.approval_step.source, submitted.approval_step.assigned_membership_id


@pytest.mark.parametrize(
    ("branch_rule", "expected_source"),
    [(True, "threshold_match"), (False, "threshold_match")],
)
def test_submitted_request_routes_to_matching_threshold_approver(
    monkeypatch: pytest.MonkeyPatch,
    branch_rule: bool,
    expected_source: Literal["threshold_match"],
) -> None:
    branch_approver_id = uuid4()
    tenant_approver_id = uuid4()
    rules = [
        threshold_rule(
            branch_id=None,
            min_amount="0",
            max_amount="1000",
            approver_id=tenant_approver_id,
        )
    ]
    service, client, member, request_id = build_service(monkeypatch, rules=rules)
    if branch_rule:
        rules.append(
            threshold_rule(
                branch_id=UUID(str(client.request_row["branch_id"])),
                min_amount="0",
                max_amount="1000",
                approver_id=branch_approver_id,
            )
        )

    source, assignee_id = submit_and_fetch_pending(service, member, request_id)

    assert source == expected_source
    assert assignee_id == (branch_approver_id if branch_rule else tenant_approver_id)


def test_active_delegation_redirects_the_threshold_resolved_assignee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approver_id = uuid4()
    delegate_id = uuid4()
    rules = [
        threshold_rule(
            branch_id=None,
            min_amount="0",
            max_amount="1000",
            approver_id=approver_id,
        )
    ]
    service, _client, member, request_id = build_service(
        monkeypatch,
        rules=rules,
        delegations=[active_delegation(delegator_id=approver_id, delegate_id=delegate_id)],
    )

    source, assignee_id = submit_and_fetch_pending(service, member, request_id)

    assert source == "delegate"
    assert assignee_id == delegate_id


def test_owner_fallback_records_escalation_when_no_rule_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = FakeAuditWriter()
    service, _client, member, request_id = build_service(monkeypatch, rules=[])
    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.get_audit_writer",
        lambda: audit,
    )

    source, assignee_id = submit_and_fetch_pending(service, member, request_id)

    assert source == "owner_fallback"
    assert assignee_id == member.membership_id
    assert audit.actions == [
        "requests.approval_step_escalated",
        "requests.purchase_request_submitted",
    ]
