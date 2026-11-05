"""ADR-025 request status transitions through real authenticated transactions."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, make_workspace
from integration.quotation_helpers import PsycopgSupabaseClient
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from integration.test_confirm_delivery import _payload as delivery_payload
from integration.test_order_tracking import _base_order_payload, _setup_approved_request
from procurepilot_api import db
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.orders.schemas import PurchaseOrderCreate, PurchaseOrderDraftUpdate
from procurepilot_api.modules.orders.service import OrdersService
from procurepilot_api.modules.requests import service as requests_module
from procurepilot_api.modules.requests.schemas import ApprovalDecisionInput
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Lifecycle:
    conn: psycopg.Connection
    member: CurrentMember
    requests: RequestsService
    orders: OrdersService
    request_id: UUID
    line_id: UUID
    payload: PurchaseOrderCreate

    def status(self) -> str:
        with self.conn.cursor() as cur:
            cur.execute("select status from purchase_request where id=%s", (self.request_id,))
            return cur.fetchone()[0]

    def set_status(self, status: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "update purchase_request set status=%s where id=%s", (status, self.request_id)
            )
        self.conn.commit()

    def create(self) -> UUID:
        payload = self.payload.model_copy(update={"order_number": f"PO-{uuid4().hex[:12]}"})
        order, created = self.orders.create_order(
            bearer_token="test", member=self.member, payload=payload, idempotency_key=uuid4()
        )
        assert created
        return order.id

    def cancel(self, order_id: UUID) -> None:
        self.orders.cancel_order(
            bearer_token="test", member=self.member, order_id=order_id, idempotency_key=uuid4()
        )

    def withdraw(self) -> None:
        response = self.requests.withdraw_request(
            bearer_token="test",
            member=self.member,
            request_id=self.request_id,
            idempotency_key=uuid4(),
        )
        assert response.status == "withdrawn"


@pytest.fixture
def lifecycle(monkeypatch: pytest.MonkeyPatch) -> Iterator[Lifecycle]:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context(f"adr025-{uuid4().hex[:12]}") as context:
        with db.connect(TEST_DATABASE_URL or "") as conn:
            rid, lid = _setup_approved_request(conn, context.workspace, context.product_id)
            member = member_from_workspace(context.workspace)
            monkeypatch.setattr(
                requests_module,
                "authenticated_client",
                lambda *_: PsycopgSupabaseClient(conn, claims=context.workspace.claims()),
            )
            monkeypatch.setattr(requests_module, "enqueue_push_job", lambda *_: None)
            result = Lifecycle(
                conn,
                member,
                RequestsService(settings),
                OrdersService(settings),
                rid,
                lid,
                PurchaseOrderCreate.model_validate(
                    _base_order_payload(
                        context.supplier_ids[0],
                        rid,
                        lid,
                        context.product_id,
                    )
                ),
            )
            result.set_status("approved")
            yield result
            conn.rollback()


@pytest.mark.parametrize("keyed", [False, True])
def test_approval_and_keyed_replay_return_current_state(lifecycle: Lifecycle, keyed: bool) -> None:
    case = lifecycle
    case.set_status("submitted")
    with case.conn.cursor() as cur:
        cur.execute(
            "update approval_step set status='pending',decided_by_membership_id=null,"
            "decided_at=null where purchase_request_id=%s",
            (case.request_id,),
        )
    case.conn.commit()
    key = uuid4() if keyed else None

    def approve():
        return case.requests.approve_request(
            bearer_token="test",
            member=case.member,
            request_id=case.request_id,
            payload=ApprovalDecisionInput(),
            idempotency_key=key,
        )

    approved = approve()
    assert approved.status == "approved"
    assert approved.approval_step.status == "approved"
    assert case.status() == "approved"
    if keyed:
        assert approve().status == "approved"
        case.create()
        assert approve().status == "ordered"
        with case.conn.cursor() as cur:
            cur.execute(
                "select count(*) from push_notification where purchase_request_id=%s",
                (case.request_id,),
            )
            assert cur.fetchone()[0] == 1


def test_first_second_cancel_and_recreate(lifecycle: Lifecycle) -> None:
    case = lifecycle
    first = case.create()
    assert case.status() == "ordered"
    second = case.create()
    assert case.status() == "ordered"
    case.cancel(first)
    assert case.status() == "ordered"
    case.cancel(second)
    assert case.status() == "approved"
    case.create()
    assert case.status() == "ordered"


def test_cancel_only_live_order(lifecycle: Lifecycle) -> None:
    order = lifecycle.create()
    lifecycle.cancel(order)
    assert lifecycle.status() == "approved"


@pytest.mark.parametrize("status", ["approved", "ordered"])
def test_live_order_prevents_withdrawal(lifecycle: Lifecycle, status: str) -> None:
    lifecycle.create()
    lifecycle.set_status(status)
    with pytest.raises(ConflictError) as error:
        lifecycle.withdraw()
    assert error.value.details == {"reason": "purchase_order_exists"}
    assert lifecycle.status() == status


@pytest.mark.parametrize("status", ["approved", "ordered"])
def test_without_live_order_can_withdraw(lifecycle: Lifecycle, status: str) -> None:
    lifecycle.set_status(status)
    lifecycle.withdraw()
    assert lifecycle.status() == "withdrawn"


def test_legacy_ordered_request_can_create_order(lifecycle: Lifecycle) -> None:
    lifecycle.set_status("ordered")
    lifecycle.create()
    assert lifecycle.status() == "ordered"


def test_delivery_requires_order(lifecycle: Lifecycle) -> None:
    case = lifecycle
    args = dict(
        bearer_token="test",
        member=case.member,
        request_id=case.request_id,
        payload=delivery_payload([(case.line_id, "10")]),
    )
    with pytest.raises(ConflictError) as error:
        case.requests.confirm_delivery(**args)
    assert error.value.details == {"reason": "not_ordered"}
    case.create()
    assert case.requests.confirm_delivery(**args).status == "delivered"


@pytest.mark.parametrize("status", ["delivered", "withdrawn", "rejected"])
def test_cancellation_preserves_terminal_request(lifecycle: Lifecycle, status: str) -> None:
    case = lifecycle
    order = case.create()
    if status == "delivered":
        case.requests.confirm_delivery(
            bearer_token="test",
            member=case.member,
            request_id=case.request_id,
            payload=delivery_payload([(case.line_id, "10")]),
        )
    else:
        case.set_status(status)
    case.cancel(order)
    assert case.status() == status


def test_draft_edit_attach_keep_and_detach(lifecycle: Lifecycle) -> None:
    case = lifecycle
    manual = case.payload.model_copy(
        update={
            "source_request_id": None,
            "lines": tuple(
                line.model_copy(update={"source_request_line_id": None})
                for line in case.payload.lines
            ),
        }
    )
    order, _ = case.orders.create_order(
        bearer_token="test",
        member=case.member,
        payload=manual,
        idempotency_key=uuid4(),
    )
    assert case.status() == "approved"
    for payload, expected in [
        (case.payload, "ordered"),
        (case.payload, "ordered"),
        (manual, "approved"),
    ]:
        case.orders.update_draft_order(
            bearer_token="test",
            member=case.member,
            order_id=order.id,
            payload=PurchaseOrderDraftUpdate.model_validate(payload.model_dump()),
            idempotency_key=uuid4(),
        )
        assert case.status() == expected


def test_other_tenant_cannot_cancel_or_change_request(lifecycle: Lifecycle) -> None:
    case = lifecycle
    order = case.create()
    with case.conn.cursor() as cur:
        other = make_workspace(cur, f"adr025-other-{uuid4().hex[:12]}")
    case.conn.commit()
    with pytest.raises(NotFoundError):
        case.orders.cancel_order(
            bearer_token="test",
            member=member_from_workspace(other),
            order_id=order,
            idempotency_key=uuid4(),
        )
    assert case.status() == "ordered"
