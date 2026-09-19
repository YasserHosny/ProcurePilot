from contextlib import nullcontext
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.orders import service as orders_service
from procurepilot_api.modules.orders.schemas import (
    DeliveryReceiptCreate,
    DeliveryReceiptLineInput,
    Money,
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderLine,
    PurchaseOrderLineInput,
    SupplierConfirmationLineInput,
)
from procurepilot_api.modules.orders.service import (
    OrdersService,
    _assert_same_order,
    _confirmation_model,
    _database_error,
    _not_found,
    _order_model,
    _receipt_model,
    _submit_action,
)
from procurepilot_api.modules.orders.validation import build_lifecycle_summary

TENANT = UUID("00000000-0000-0000-0000-000000000001")
MEMBER = UUID("00000000-0000-0000-0000-000000000002")
ORDER = UUID("00000000-0000-0000-0000-000000000003")
LINE = UUID("00000000-0000-0000-0000-000000000004")


def _member(role: MemberRole = MemberRole.buyer) -> CurrentMember:
    return CurrentMember(
        membership_id=MEMBER,
        tenant_id=TENANT,
        user_id=UUID("00000000-0000-0000-0000-000000000005"),
        email="buyer@example.test",
        role=role,
    )


def _order() -> PurchaseOrder:
    now = datetime(2026, 9, 19, tzinfo=UTC)
    return PurchaseOrder(
        id=ORDER,
        tenant_id=TENANT,
        order_number="PO-1",
        supplier_id=UUID("00000000-0000-0000-0000-000000000006"),
        status="submitted",
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_kind="manual",
        source_reference="manual:PO-1",
        created_by=MEMBER,
        created_at=now,
        updated_at=now,
        lines=(
            PurchaseOrderLine(
                id=LINE,
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("10"),
                base_unit="each",
                unit_price=Money(amount=Decimal("1"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
            ),
        ),
    )


def test_lifecycle_accumulates_partial_multiple_receipts_without_zero_for_missing_evidence() -> (
    None
):
    order = _order()
    first = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-1",
        receipt_date=date(2026, 9, 20),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="grn:1",
        source_hash=None,
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        lines=(
            SimpleNamespace(
                id=UUID(int=11), purchase_order_line_id=LINE, received_quantity=Decimal("4")
            ),
        ),
    )
    second = SimpleNamespace(
        **{
            **first.__dict__,
            "id": UUID("00000000-0000-0000-0000-000000000011"),
            "receipt_reference": "GRN-2",
            "receipt_date": date(2026, 9, 21),
            "lines": (
                SimpleNamespace(
                    id=UUID(int=12), purchase_order_line_id=LINE, received_quantity=Decimal("3")
                ),
            ),
        }
    )
    # The validator accepts the same structural contract as the API response models.
    summary = build_lifecycle_summary(order, receipts=(first, second))
    assert summary.status == "partially_received"
    assert summary.lines[0].received.quantity == Decimal("7")
    assert summary.lines[0].remaining_quantity == Decimal("3")


def test_write_requires_owner_or_buyer_and_idempotency_key() -> None:
    with pytest.raises(PermissionDeniedError):
        OrdersService._require_write(_member(MemberRole.viewer), UUID(int=1))
    with pytest.raises(UnprocessableEntityError):
        OrdersService._require_write(_member(), None)


def test_tenant_scoped_empty_result_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        _not_found([], "purchase_order")


def test_submit_replay_is_noop_and_status_transition_is_guarded() -> None:
    key = UUID(int=31)
    assert _submit_action({"status": "submitted", "submit_idempotency_key": key}, key) == "replay"
    with pytest.raises(ConflictError):
        _submit_action({"status": "submitted", "submit_idempotency_key": None}, key)


def test_evidence_idempotency_key_cannot_cross_orders() -> None:
    with pytest.raises(ConflictError):
        _assert_same_order({"purchase_order_id": str(UUID(int=99))}, ORDER)


def test_boundary_decimal_scales_match_database_precision() -> None:
    assert Money(amount=Decimal("0"), currency="USD").amount == Decimal("0")
    with pytest.raises(ValueError):
        Money(amount=Decimal("1.00001"), currency="USD")
    with pytest.raises(ValueError):
        PurchaseOrderLineInput(
            line_number=1,
            description="Widget",
            ordered_quantity=Decimal("1.0000001"),
            base_unit="each",
            unit_price=Money(amount=Decimal("1"), currency="USD"),
            tax=Money(amount=Decimal("0"), currency="USD"),
            line_total=Money(amount=Decimal("1"), currency="USD"),
        )
    with pytest.raises(ValueError):
        SupplierConfirmationLineInput(
            purchase_order_line_id=LINE, confirmed_quantity=Decimal("1.0000001")
        )
    with pytest.raises(ValueError):
        DeliveryReceiptLineInput(
            purchase_order_line_id=LINE, received_quantity=Decimal("1.0000001")
        )


def test_transaction_sqlstate_mapping_is_consistent() -> None:
    assert isinstance(_database_error(SimpleNamespace(sqlstate="23505")), ConflictError)
    assert isinstance(_database_error(SimpleNamespace(sqlstate="23503")), UnprocessableEntityError)
    assert isinstance(_database_error(SimpleNamespace(sqlstate="22P02")), UnprocessableEntityError)
    assert isinstance(_database_error(SimpleNamespace(sqlstate="08006")), ServiceUnavailableError)


class _FakeTable:
    def __init__(self, name: str, rows: dict[str, list[dict[str, object]]]) -> None:
        self.name = name
        self.rows = rows
        self.filters: dict[str, str] = {}
        self.operation = "select"
        self.payload: object = None

    def select(self, _columns: str) -> "_FakeTable":
        return self

    def eq(self, key: str, value: str) -> "_FakeTable":
        self.filters[key] = value
        return self

    def limit(self, _value: int) -> "_FakeTable":
        return self

    def insert(self, payload: object) -> "_FakeTable":
        self.operation = "insert"
        self.payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "insert":
            identifier = UUID(int=20 if self.name == "delivery_receipt" else 21)
            return SimpleNamespace(data=[{"id": str(identifier)}])
        return SimpleNamespace(data=self.rows.get(self.name, []))


class _FakeClient:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, object]]] = {
            "delivery_receipt_line": [],
            "supplier_confirmation_line": [],
        }
        self.tables: list[_FakeTable] = []

    def table(self, name: str) -> _FakeTable:
        table = _FakeTable(name, self.rows)
        self.tables.append(table)
        return table


class _FakeCursor:
    def __init__(self) -> None:
        self.last_row: dict[str, object] | None = None

    def execute(self, statement: str, _params: object = None) -> None:
        if "record_audit_event" not in statement:
            self.last_row = {"id": str(UUID(int=20))}

    def executemany(self, _statement: str, _params: object) -> None:
        return None

    def fetchone(self) -> dict[str, object] | None:
        return self.last_row


class _RollbackContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor = cursor
        self.rolled_back = False

    def __enter__(self) -> _FakeCursor:
        return self.cursor

    def __exit__(self, exc_type: object, _value: object, _traceback: object) -> bool:
        self.rolled_back = exc_type is not None
        return False


def test_failed_line_insert_rolls_back_header_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = _FakeCursor()
    transaction = _RollbackContext(cursor)

    def fail_lines(_statement: str, _params: object) -> None:
        raise RuntimeError("line insert failed")

    cursor.executemany = fail_lines  # type: ignore[method-assign]
    service = OrdersService.__new__(OrdersService)
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)
    payload = PurchaseOrderCreate(
        order_number="PO-rollback",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:rollback",
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("10"),
                base_unit="each",
                unit_price=Money(amount=Decimal("1"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
            ),
        ),
    )
    with pytest.raises(RuntimeError):
        service.create_order(
            bearer_token="token", member=_member(), payload=payload, idempotency_key=UUID(int=50)
        )
    assert transaction.rolled_back is True


def test_flattened_order_rows_map_without_idempotency_extras() -> None:
    raw = {
        "id": str(ORDER),
        "tenant_id": str(TENANT),
        "order_number": "PO-1",
        "supplier_id": "00000000-0000-0000-0000-000000000006",
        "status": "draft",
        "order_date": date(2026, 9, 19),
        "expected_delivery_date": None,
        "total_amount": "10",
        "total_currency": "USD",
        "tax_amount": "0",
        "tax_currency": "USD",
        "source_kind": "manual",
        "source_reference": "manual:PO-1",
        "source_hash": None,
        "created_by": str(MEMBER),
        "created_at": datetime(2026, 9, 19, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
        "idempotency_key": str(UUID(int=30)),
        "submit_idempotency_key": None,
    }
    line = {
        "id": str(LINE),
        "line_number": 1,
        "workspace_product_id": None,
        "description": "Widget",
        "ordered_quantity": "10",
        "base_unit": "each",
        "unit_price_amount": "1",
        "unit_price_currency": "USD",
        "tax_amount": "0",
        "tax_currency": "USD",
        "line_total_amount": "10",
        "line_total_currency": "USD",
    }
    assert _order_model(raw, [line]).id == ORDER


def test_flattened_confirmation_and_receipt_rows_map_explicitly() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    confirmation = _confirmation_model(
        {
            "id": str(UUID(int=40)),
            "tenant_id": str(TENANT),
            "purchase_order_id": str(ORDER),
            "supplier_reference": "ACK-1",
            "confirmed_at": now,
            "expected_delivery_date": None,
            "source_kind": "manual",
            "source_reference": "ack:1",
            "source_hash": None,
            "recorded_by": str(MEMBER),
            "created_at": now,
            "idempotency_key": str(UUID(int=41)),
        },
        [
            {
                "id": str(UUID(int=42)),
                "purchase_order_line_id": str(LINE),
                "confirmed_quantity": "10",
                "confirmed_unit_price_amount": None,
                "confirmed_unit_price_currency": None,
            }
        ],
    )
    receipt = _receipt_model(
        {
            "id": str(UUID(int=43)),
            "tenant_id": str(TENANT),
            "purchase_order_id": str(ORDER),
            "receipt_reference": "GRN-1",
            "receipt_date": date(2026, 9, 20),
            "received_by": str(MEMBER),
            "source_kind": "manual",
            "source_reference": "grn:1",
            "source_hash": None,
            "created_at": now,
            "idempotency_key": str(UUID(int=44)),
        },
        [{"id": str(UUID(int=45)), "purchase_order_line_id": str(LINE), "received_quantity": "4"}],
    )
    assert confirmation.lines[0].confirmed_quantity == Decimal("10")
    assert receipt.lines[0].received_quantity == Decimal("4")


def test_receipt_insertion_and_audit_are_called(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    audit_calls: list[object] = []
    monkeypatch.setattr(orders_service, "authenticated_client", lambda _settings, _token: fake)
    monkeypatch.setattr(OrdersService, "_load_order", lambda _self, _client, _id: _order())
    monkeypatch.setattr(OrdersService, "_evidence", lambda _self, _client, _id: "evidence")
    monkeypatch.setattr(
        OrdersService, "_transaction", lambda _self, _member: nullcontext(_FakeCursor())
    )
    monkeypatch.setattr(OrdersService, "_load_receipt_cursor", lambda *_args: "receipt")
    monkeypatch.setattr(OrdersService, "_audit_cursor", lambda *_args: audit_calls.append(True))
    payload = DeliveryReceiptCreate(
        receipt_reference="GRN-1",
        receipt_date=date(2026, 9, 20),
        source_reference="grn:1",
        lines=(
            DeliveryReceiptLineInput(purchase_order_line_id=LINE, received_quantity=Decimal("4")),
        ),
    )
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    result = service.record_receipt(
        bearer_token="token",
        member=_member(),
        order_id=ORDER,
        payload=payload,
        idempotency_key=UUID(int=30),
    )
    assert result == "evidence"
    assert audit_calls == [True]


def test_migration_has_tenant_scoped_nullable_header_keys() -> None:
    migration = open("supabase/migrations/20260919000008_order_tracking_idempotency.sql").read()
    assert "add column if not exists idempotency_key uuid" in migration
    assert "where idempotency_key is not null" in migration
