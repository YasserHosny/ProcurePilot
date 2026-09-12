"""Request budget-status integration coverage — task T039.

The pure calculation is covered in ``test_budget_status.py``. These tests prove the request
service attaches that calculation to both public read paths that expose request context, and
that an over-budget warning remains informational: it must not block a human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests.budget_status import BudgetRow, SpendRow
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.shared.audit import AuditEventCreate


@dataclass
class Response:
    data: list[dict[str, object]]


class FakeQuery:
    def __init__(self, client: FakeClient, table: str) -> None:
        self.client = client
        self.table = table
        self.update_body: dict[str, object] | None = None
        self.filters: dict[str, object] = {}

    def select(self, _columns: str) -> FakeQuery:
        return self

    def update(self, body: dict[str, object]) -> FakeQuery:
        self.update_body = body
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self.filters[column] = value
        return self

    def in_(self, column: str, value: object) -> FakeQuery:
        self.filters[column] = value
        return self

    def order(self, _column: str, *, desc: bool = False) -> FakeQuery:
        return self

    def range(self, _start: int, _end: int) -> FakeQuery:
        return self

    def limit(self, _count: int) -> FakeQuery:
        return self

    def execute(self) -> Response:
        if self.update_body is None:
            if self.table == "approval_step":
                return Response([self.client.step_row])
            return Response([])

        if self.table == "purchase_request":
            self.client.request_row.update(self.update_body)
            return Response([self.client.request_row])
        if self.table == "approval_step":
            self.client.step_row.update(self.update_body)
            return Response([self.client.step_row])
        raise AssertionError(f"unexpected table update: {self.table}")


class FakeClient:
    def __init__(
        self,
        request_row: dict[str, object],
        step_row: dict[str, object],
    ) -> None:
        self.request_row = request_row
        self.step_row = step_row

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
    status: str = "submitted",
    amount: str = "120.0000",
) -> dict[str, object]:
    return {
        "id": str(request_id),
        "tenant_id": str(tenant_id),
        "branch_id": str(branch_id),
        "cost_centre_id": None,
        "requested_by_membership_id": str(requester_id),
        "required_by_date": "2026-09-15",
        "status": status,
        "estimated_total_amount": amount,
        "estimated_total_currency": "GBP",
        "has_incomplete_estimate": False,
        "submitted_at": "2026-09-11T09:00:00Z",
        "withdrawn_at": None,
        "created_at": "2026-09-11T08:55:00Z",
        "updated_at": "2026-09-11T09:00:00Z",
    }


def line_row(*, request_id: UUID, product_id: UUID) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "purchase_request_id": str(request_id),
        "workspace_product_id": str(product_id),
        "quantity": "12.000000",
        "note": None,
        "estimated_unit_price_amount": "10.0000",
        "estimated_unit_price_currency": "GBP",
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": "2026-09-11T09:00:00Z",
    }


def step_row(*, request_id: UUID, assignee_id: UUID) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "purchase_request_id": str(request_id),
        "assigned_membership_id": str(assignee_id),
        "source": "owner_fallback",
        "status": "pending",
        "comment": None,
        "decided_by_membership_id": None,
        "decided_at": None,
    }


def owner_member(
    *, tenant_id: UUID, membership_id: UUID, user_id: UUID | None = None
) -> CurrentMember:
    return CurrentMember(
        tenant_id=tenant_id,
        membership_id=membership_id,
        user_id=user_id or uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )


def budget(branch_id: UUID) -> BudgetRow:
    return BudgetRow(
        id=uuid4(),
        amount=Decimal("100.0000"),
        currency="GBP",
        period="monthly",
        period_start=date(2026, 9, 1),
        scope="branch",
        branch_id=branch_id,
        cost_centre_id=None,
    )


def spend(*, request_id: UUID, branch_id: UUID, amount: str) -> SpendRow:
    return SpendRow(
        request_id=request_id,
        amount=Decimal(amount),
        currency="GBP",
        branch_id=branch_id,
        cost_centre_id=None,
        required_by_date=date(2026, 9, 12),
    )


def service_with_budget_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RequestsService, FakeClient, CurrentMember, UUID]:
    tenant_id = uuid4()
    branch_id = uuid4()
    requester_id = uuid4()
    approver_id = uuid4()
    request_id = uuid4()
    product_id = uuid4()
    req = request_row(
        request_id=request_id,
        tenant_id=tenant_id,
        branch_id=branch_id,
        requester_id=requester_id,
    )
    step = step_row(request_id=request_id, assignee_id=approver_id)
    client = FakeClient(req, step)
    service = RequestsService()
    member = owner_member(tenant_id=tenant_id, membership_id=approver_id)

    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.authenticated_client",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(service, "_fetch_request", lambda _client, _id: req)
    monkeypatch.setattr(
        service,
        "_fetch_lines_for",
        lambda _client, _id: [
            line_row(request_id=request_id, product_id=product_id)
        ],
    )
    monkeypatch.setattr(service, "_fetch_step", lambda _client, _id: step)
    monkeypatch.setattr(service, "_fetch_requests_batch", lambda _client, _ids: [req])
    monkeypatch.setattr(
        service,
        "_fetch_lines_batch",
        lambda _client, _ids: {
            str(request_id): [
                line_row(request_id=request_id, product_id=product_id)
            ]
        },
    )
    monkeypatch.setattr(service, "_fetch_budget_rows", lambda _client: [budget(branch_id)])
    monkeypatch.setattr(
        service,
        "_fetch_committed_spend_rows",
        lambda _client: [spend(request_id=uuid4(), branch_id=branch_id, amount="30.0000")],
    )

    return service, client, member, request_id


def test_budget_status_is_attached_to_request_detail_and_pending_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _client, member, request_id = service_with_budget_fixture(monkeypatch)

    detail = service.get_request(bearer_token="token", request_id=request_id)
    pending = service.list_pending_approvals(
        bearer_token="token",
        member=member,
    )

    assert detail.budget_status is not None
    assert detail.budget_status.exceeds is True
    assert detail.budget_status.remaining_amount.amount == "70.0000"
    assert detail.budget_status.remaining_amount.currency == "GBP"

    queued = pending.items[0]
    assert queued.id == request_id
    assert queued.budget_status is not None
    assert queued.budget_status.exceeds is True
    assert queued.budget_status.remaining_amount.amount == "70.0000"
    assert queued.budget_status.remaining_amount.currency == "GBP"


def test_exceeding_budget_does_not_block_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # _decide_and_notify (T037) is a raw-psycopg transaction, not mockable through FakeClient's
    # PostgREST-style interface (see tests/unit/test_approval_decisions.py's own note on this) —
    # faked here so this test can still exercise budget-status attachment and audit recording in
    # isolation. The atomic-write guarantee itself is proven for real against Postgres in
    # tests/integration/test_decision_atomicity.py.
    service, _client, member, request_id = service_with_budget_fixture(monkeypatch)
    audit = FakeAuditWriter()
    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.get_audit_writer",
        lambda: audit,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.requests.service.enqueue_push_job",
        lambda _settings, _notification_id: None,
    )

    def fake_decide_and_notify(**kwargs: object) -> tuple[dict, dict, UUID]:
        decided_request = dict(_client.request_row, status="approved")
        decided_step = dict(
            _client.step_row,
            status="approved",
            comment=kwargs["comment"],
            decided_by_membership_id=str(member.membership_id),
            decided_at=kwargs["now"],
        )
        return decided_request, decided_step, uuid4()

    monkeypatch.setattr(service, "_decide_and_notify", fake_decide_and_notify)

    decided = service.approve_request(
        bearer_token="token",
        member=member,
        request_id=request_id,
        payload=ApprovalDecisionInput(comment="Approved despite budget warning"),
    )

    assert decided.status == "approved"
    assert decided.approval_step is not None
    assert decided.approval_step.status == "approved"
    assert decided.approval_step.decided_by_membership_id == member.membership_id
    assert decided.budget_status is not None
    assert decided.budget_status.exceeds is True
    assert audit.actions == ["requests.approval_step_approved"]
