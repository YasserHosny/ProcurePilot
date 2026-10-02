from contextlib import nullcontext
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
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


def test_purchase_order_draft_update_schema() -> None:
    from pydantic import ValidationError

    from procurepilot_api.modules.orders.schemas import PurchaseOrderDraftUpdate

    # Valid payload with source IDs
    update = PurchaseOrderDraftUpdate(
        order_number="PO-123",
        supplier_id=UUID("00000000-0000-0000-0000-000000000001"),
        order_date=date(2026, 1, 1),
        total={"amount": "100.00", "currency": "USD"},
        tax={"amount": "0.00", "currency": "USD"},
        source_reference="123",
        source_request_id=UUID("00000000-0000-0000-0000-000000000002"),
        lines=[
            {
                "line_number": 1,
                "description": "Widget",
                "ordered_quantity": "10",
                "base_unit": "each",
                "unit_price": {"amount": "10.00", "currency": "USD"},
                "tax": {"amount": "0.00", "currency": "USD"},
                "line_total": {"amount": "100.00", "currency": "USD"},
                "source_request_line_id": UUID("00000000-0000-0000-0000-000000000003"),
            }
        ],
    )
    assert update.source_request_id == UUID("00000000-0000-0000-0000-000000000002")
    assert update.lines[0].source_request_line_id == UUID("00000000-0000-0000-0000-000000000003")

    # Reusing StrictModel forbids extra fields
    with pytest.raises(ValidationError):
        PurchaseOrderDraftUpdate(
            order_number="PO-123",
            supplier_id=UUID("00000000-0000-0000-0000-000000000001"),
            order_date=date(2026, 1, 1),
            total={"amount": "100.00", "currency": "USD"},
            tax={"amount": "0.00", "currency": "USD"},
            source_reference="123",
            lines=[
                {
                    "line_number": 1,
                    "description": "Widget",
                    "ordered_quantity": "10",
                    "base_unit": "each",
                    "unit_price": {"amount": "10.00", "currency": "USD"},
                    "tax": {"amount": "0.00", "currency": "USD"},
                    "line_total": {"amount": "100.00", "currency": "USD"},
                }
            ],
            extra_field="invalid",
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


class _FakeConnection:
    def transaction(self) -> "_FakeConnection":
        return self

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        pass


class _FakeCursor:
    def __init__(self) -> None:
        self.last_row: dict[str, object] | None = None
        self.executed: list[tuple[str, object]] = []
        self.connection = _FakeConnection()

    def execute(self, statement: str, params: object = None) -> None:
        self.executed.append((statement, params))
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
        "source_request_id": str(UUID(int=88)),
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
        "source_request_line_id": str(UUID(int=99)),
    }
    order = _order_model(raw, [line])
    assert order.id == ORDER
    assert order.source_request_id == UUID(int=88)
    assert order.lines[0].source_request_line_id == UUID(int=99)


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
    migration_path = (
        Path(__file__).resolve().parents[4]
        / "supabase"
        / "migrations"
        / "20260919000008_order_tracking_idempotency.sql"
    )
    migration = migration_path.read_text()
    assert "add column if not exists idempotency_key uuid" in migration
    assert "where idempotency_key is not null" in migration


def test_create_order_validates_request_linkage(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from procurepilot_api.modules.requests.service import RequestsService

    req_id = UUID(int=7)
    line_id = UUID(int=8)
    product_id = UUID(int=9)

    cursor = _FakeCursor()
    cursor.fetchall = lambda: [{"source_request_line_id": str(line_id), "allocated": Decimal("5")}]  # type: ignore[attr-defined]

    transaction = _RollbackContext(cursor)
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)
    monkeypatch.setattr(OrdersService, "_load_order_cursor", lambda _self, _cur, _id: None)
    monkeypatch.setattr(OrdersService, "_audit_cursor", lambda _self, _cur, _mem, _evt, _id: None)

    mock_request = SimpleNamespace(
        lines=[
            SimpleNamespace(
                id=line_id,
                workspace_product_id=product_id,
                quantity=Decimal("10"),
            )
        ]
    )
    monkeypatch.setattr(
        RequestsService, "validate_approved_request_for_order", lambda *a, **k: mock_request
    )

    # 1. Valid allocation (remaining is 5)
    valid_payload = PurchaseOrderCreate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("5"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )

    # Should succeed without exception
    service.create_order(
        bearer_token="token", member=_member(), payload=valid_payload, idempotency_key=UUID(int=10)
    )

    # 2. Exceeds allocation (ordered 6, remaining 5)
    payload_exceeds = PurchaseOrderCreate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("12"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("6"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("12"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )
    with pytest.raises(ConflictError) as exc_info:
        service.create_order(
            bearer_token="token",
            member=_member(),
            payload=payload_exceeds,
            idempotency_key=UUID(int=11),
        )
    assert exc_info.value.details == {"reason": "quantity_exceeds_allocation"}

    # 2b. Duplicate incoming lines over-allocate in aggregate (ordered 3 + 3 = 6, remaining 5)
    payload_exceeds_aggregate = PurchaseOrderCreate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("12"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("3"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("6"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
            PurchaseOrderLineInput(
                line_number=2,
                description="Widget 2",
                ordered_quantity=Decimal("3"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("6"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )
    with pytest.raises(ConflictError) as exc_info_agg:
        service.create_order(
            bearer_token="token",
            member=_member(),
            payload=payload_exceeds_aggregate,
            idempotency_key=UUID(int=14),
        )
    assert exc_info_agg.value.details == {"reason": "quantity_exceeds_allocation"}

    # 3. Missing source_request_line_id
    payload_missing = PurchaseOrderCreate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("5"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
                source_request_line_id=None,
                workspace_product_id=product_id,
            ),
        ),
    )
    with pytest.raises(UnprocessableEntityError) as exc_info_missing:
        service.create_order(
            bearer_token="token",
            member=_member(),
            payload=payload_missing,
            idempotency_key=UUID(int=12),
        )
    assert exc_info_missing.value.details == {"reason": "missing_source_request_line_id"}

    # 4. Orphan source_request_line_id (no header source_request_id)
    payload_orphan = PurchaseOrderCreate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=None,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("5"),
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )
    with pytest.raises(UnprocessableEntityError) as exc_info_orphan:
        service.create_order(
            bearer_token="token",
            member=_member(),
            payload=payload_orphan,
            idempotency_key=UUID(int=13),
        )
    assert exc_info_orphan.value.details == {"reason": "orphan_source_request_line_id"}


def test_update_draft_order_idempotency_and_allocations(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from procurepilot_api.modules.orders.schemas import PurchaseOrderDraftUpdate
    from procurepilot_api.modules.requests.service import RequestsService

    req_id = UUID(int=7)
    line_id = UUID(int=8)
    product_id = UUID(int=9)
    order_id = UUID(int=20)
    idempotency_key = UUID(int=99)

    cursor = _FakeCursor()
    # Mock for allocation check: return 2 allocated (from other orders)
    cursor.fetchall = lambda: [{"source_request_line_id": str(line_id), "allocated": Decimal("2")}]  # type: ignore[attr-defined]

    # Mock fetchone to return the order first, then None for idempotency/number checks
    call_count = 0

    def mock_fetchone() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call is locking the order
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-orig",
                "supplier_id": str(UUID(int=6)),
                "status": "draft",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual:link",
                "source_hash": None,
                "source_request_id": str(req_id),
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": None,
            }
        return None

    cursor.fetchone = mock_fetchone  # type: ignore[method-assign]

    transaction = _RollbackContext(cursor)
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)
    monkeypatch.setattr(OrdersService, "_load_order_cursor", lambda _self, _cur, _id: None)
    monkeypatch.setattr(OrdersService, "_audit_cursor", lambda _self, _cur, _mem, _evt, _id: None)

    mock_request = SimpleNamespace(
        lines=[
            SimpleNamespace(
                id=line_id,
                workspace_product_id=product_id,
                quantity=Decimal("10"),
            )
        ]
    )
    monkeypatch.setattr(
        RequestsService, "validate_approved_request_for_order", lambda *a, **k: mock_request
    )

    # 1. Valid edit
    valid_payload = PurchaseOrderDraftUpdate(
        order_number="PO-link",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual:link",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="Widget",
                ordered_quantity=Decimal("8"),  # 10 req - 2 alloc = 8 remaining
                base_unit="each",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )

    service.update_draft_order(
        bearer_token="token",
        member=_member(),
        order_id=order_id,
        payload=valid_payload,
        idempotency_key=idempotency_key,
    )

    # 2. Exceeds allocation
    call_count = 0
    payload_exceeds = valid_payload.model_copy(deep=True)
    payload_exceeds.lines = (
        PurchaseOrderLineInput(
            line_number=1,
            description="Widget",
            ordered_quantity=Decimal("9"),  # 9 > 8 remaining
            base_unit="each",
            unit_price=Money(amount=Decimal("2"), currency="USD"),
            tax=Money(amount=Decimal("0"), currency="USD"),
            line_total=Money(amount=Decimal("18"), currency="USD"),
            source_request_line_id=line_id,
            workspace_product_id=product_id,
        ),
    )
    with pytest.raises(ConflictError) as exc_info:
        service.update_draft_order(
            bearer_token="token",
            member=_member(),
            order_id=order_id,
            payload=payload_exceeds,
            idempotency_key=idempotency_key,
        )
    assert exc_info.value.details == {"reason": "quantity_exceeds_allocation"}

    # 3. Idempotent replay
    call_count = 0

    def mock_fetchone_replay() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-orig",
                "supplier_id": str(UUID(int=6)),
                "status": "draft",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual:link",
                "source_hash": None,
                "source_request_id": str(req_id),
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": str(idempotency_key),
            }
        return None

    cursor.fetchone = mock_fetchone_replay  # type: ignore[method-assign]

    # Should not raise exception and should not execute updates
    service.update_draft_order(
        bearer_token="token",
        member=_member(),
        order_id=order_id,
        payload=valid_payload,
        idempotency_key=idempotency_key,
    )


def test_order_mutations_acquire_advisory_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from procurepilot_api.modules.orders.schemas import PurchaseOrderDraftUpdate
    from procurepilot_api.modules.requests.service import RequestsService

    req_id = UUID(int=7)
    line_id = UUID(int=8)
    product_id = UUID(int=9)
    order_id = UUID(int=20)
    tenant_id = TENANT

    cursor = _FakeCursor()
    cursor.fetchall = lambda: []  # type: ignore[attr-defined]

    transaction = _RollbackContext(cursor)
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)
    monkeypatch.setattr(OrdersService, "_load_order_cursor", lambda _self, _cur, _id: None)
    monkeypatch.setattr(OrdersService, "_audit_cursor", lambda _self, _cur, _mem, _evt, _id: None)

    mock_request = SimpleNamespace(
        lines=[
            SimpleNamespace(
                id=line_id,
                workspace_product_id=product_id,
                quantity=Decimal("10"),
            )
        ]
    )
    monkeypatch.setattr(
        RequestsService, "validate_approved_request_for_order", lambda *a, **k: mock_request
    )

    create_payload = PurchaseOrderCreate(
        order_number="PO-lock",
        supplier_id=UUID(int=6),
        order_date=date(2026, 9, 19),
        total=Money(amount=Decimal("10"), currency="USD"),
        tax=Money(amount=Decimal("0"), currency="USD"),
        source_reference="manual",
        source_request_id=req_id,
        lines=(
            PurchaseOrderLineInput(
                line_number=1,
                description="W",
                ordered_quantity=Decimal("5"),
                base_unit="ea",
                unit_price=Money(amount=Decimal("2"), currency="USD"),
                tax=Money(amount=Decimal("0"), currency="USD"),
                line_total=Money(amount=Decimal("10"), currency="USD"),
                source_request_line_id=line_id,
                workspace_product_id=product_id,
            ),
        ),
    )

    service.create_order(
        bearer_token="token", member=_member(), payload=create_payload, idempotency_key=UUID(int=10)
    )

    expected_lock_id = (tenant_id.int ^ req_id.int) & 0x7FFFFFFFFFFFFFFF
    lock_statements = [stmt for stmt, params in cursor.executed if "pg_advisory_xact_lock" in stmt]
    assert len(lock_statements) == 1
    # Check that it passed expected_lock_id
    lock_calls = [params for stmt, params in cursor.executed if "pg_advisory_xact_lock" in stmt]
    assert lock_calls[0] == (expected_lock_id,)

    # Now test update locking old + new requests
    cursor.executed.clear()
    old_req_id = UUID(int=77)

    call_count = 0

    def mock_fetchone() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call is locking the order row
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-lock",
                "supplier_id": str(UUID(int=6)),
                "status": "draft",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual",
                "source_hash": None,
                "source_request_id": str(old_req_id),  # old request id
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": None,
            }
        return None

    cursor.fetchone = mock_fetchone  # type: ignore[method-assign]

    update_payload = PurchaseOrderDraftUpdate(**create_payload.model_dump())
    service.update_draft_order(
        bearer_token="token",
        member=_member(),
        order_id=order_id,
        payload=update_payload,
        idempotency_key=UUID(int=11),
    )

    lock_calls_update = [
        params for stmt, params in cursor.executed if "pg_advisory_xact_lock" in stmt
    ]
    assert len(lock_calls_update) == 2

    old_lock_id = (tenant_id.int ^ old_req_id.int) & 0x7FFFFFFFFFFFFFFF
    new_lock_id = (tenant_id.int ^ req_id.int) & 0x7FFFFFFFFFFFFFFF

    # Deterministic order based on UUID sort
    if old_req_id < req_id:
        assert lock_calls_update == [(old_lock_id,), (new_lock_id,)]
    else:
        assert lock_calls_update == [(new_lock_id,), (old_lock_id,)]


def test_cancel_order(monkeypatch: pytest.MonkeyPatch) -> None:
    order_id = UUID(int=20)
    tenant_id = TENANT
    req_id = UUID(int=7)
    idempotency_key = UUID(int=99)

    cursor = _FakeCursor()
    cursor.fetchall = lambda: []  # type: ignore[attr-defined]

    transaction = _RollbackContext(cursor)
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)
    monkeypatch.setattr(
        OrdersService,
        "_load_order_cursor",
        lambda _self, _cur, _id: PurchaseOrder.model_construct(id=order_id),
    )  # type: ignore
    monkeypatch.setattr(OrdersService, "_audit_cursor", lambda _self, _cur, _mem, _evt, _id: None)

    # 1. Valid cancel
    call_count = 0

    def mock_fetchone() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-orig",
                "supplier_id": str(UUID(int=6)),
                "status": "draft",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual",
                "source_hash": None,
                "source_request_id": str(req_id),
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": None,
                "cancel_idempotency_key": None,
            }
        return None

    cursor.fetchone = mock_fetchone  # type: ignore[method-assign]

    res = service.cancel_order(
        bearer_token="token", member=_member(), order_id=order_id, idempotency_key=idempotency_key
    )
    assert res.id == order_id

    # Check lock invocation
    expected_lock_id = (tenant_id.int ^ req_id.int) & 0x7FFFFFFFFFFFFFFF
    lock_calls = [params for stmt, params in cursor.executed if "pg_advisory_xact_lock" in stmt]
    assert lock_calls == [(expected_lock_id,)]

    # Check evidence retention (no delete queries)
    deletes = [stmt for stmt, params in cursor.executed if "delete" in stmt.lower()]
    assert not deletes

    # Check update status
    updates = [
        stmt
        for stmt, params in cursor.executed
        if "update purchase_order set status = 'cancelled'" in stmt.lower()
    ]
    assert len(updates) == 1

    # 2. Replay
    cursor.executed.clear()
    call_count = 0

    def mock_fetchone_replay() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-orig",
                "supplier_id": str(UUID(int=6)),
                "status": "cancelled",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual",
                "source_hash": None,
                "source_request_id": str(req_id),
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": None,
                "cancel_idempotency_key": str(idempotency_key),
            }
        return None

    cursor.fetchone = mock_fetchone_replay  # type: ignore[method-assign]

    service.cancel_order(
        bearer_token="token", member=_member(), order_id=order_id, idempotency_key=idempotency_key
    )
    # Should not run updates
    updates_replay = [
        stmt for stmt, params in cursor.executed if "update purchase_order" in stmt.lower()
    ]
    assert not updates_replay

    # 3. Bad status
    call_count = 0

    def mock_fetchone_bad_status() -> dict[str, object] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "id": str(order_id),
                "tenant_id": str(TENANT),
                "order_number": "PO-orig",
                "supplier_id": str(UUID(int=6)),
                "status": "received",
                "order_date": date(2026, 9, 19),
                "expected_delivery_date": None,
                "total_amount": "10",
                "total_currency": "USD",
                "tax_amount": "0",
                "tax_currency": "USD",
                "source_kind": "manual",
                "source_reference": "manual",
                "source_hash": None,
                "source_request_id": str(req_id),
                "created_by": str(MEMBER),
                "created_at": datetime(2026, 9, 19, tzinfo=UTC),
                "updated_at": datetime(2026, 9, 19, tzinfo=UTC),
                "submit_idempotency_key": None,
                "edit_idempotency_key": None,
                "cancel_idempotency_key": None,
            }
        return None

    cursor.fetchone = mock_fetchone_bad_status  # type: ignore[method-assign]

    with pytest.raises(ConflictError) as exc_info:
        service.cancel_order(
            bearer_token="token",
            member=_member(),
            order_id=order_id,
            idempotency_key=idempotency_key,
        )
    assert exc_info.value.details == {"reason": "order_not_cancellable"}

    # 4. Missing order
    call_count = 0

    def mock_fetchone_missing() -> dict[str, object] | None:
        return None

    cursor.fetchone = mock_fetchone_missing  # type: ignore[method-assign]
    with pytest.raises(NotFoundError):
        service.cancel_order(
            bearer_token="token",
            member=_member(),
            order_id=order_id,
            idempotency_key=idempotency_key,
        )


def test_allocation_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    req_id = UUID(int=7)
    line_id1 = UUID(int=8)
    line_id2 = UUID(int=9)

    cursor = _FakeCursor()
    transaction = _RollbackContext(cursor)
    service = OrdersService.__new__(OrdersService)
    service._settings = None
    monkeypatch.setattr(OrdersService, "_transaction", lambda _self, _member: transaction)

    from types import SimpleNamespace

    from procurepilot_api.modules.requests.service import RequestsService

    mock_request = SimpleNamespace(
        lines=[
            SimpleNamespace(id=line_id1, quantity=Decimal("10.0")),
            SimpleNamespace(id=line_id2, quantity=Decimal("5.0")),
        ]
    )
    monkeypatch.setattr(RequestsService, "get_request", lambda *a, **k: mock_request)

    # Return mock allocation rows from the SQL query
    def mock_fetchall() -> list[dict[str, object]]:
        return [
            {"source_request_line_id": str(line_id1), "allocated_quantity": Decimal("4.5")},
            # line 2 has no allocation returned
        ]

    cursor.fetchall = mock_fetchall  # type: ignore[method-assign]

    res = service.get_request_allocation(
        bearer_token="token", member=_member(), source_request_id=req_id
    )
    assert res.source_request_id == req_id
    assert len(res.lines) == 2

    # verify line 1
    l1 = next(
        line_alloc for line_alloc in res.lines if line_alloc.source_request_line_id == line_id1
    )
    assert l1.requested_quantity == Decimal("10.0")
    assert l1.allocated_quantity == Decimal("4.5")
    assert l1.remaining_quantity == Decimal("5.5")

    # verify line 2 (implicit 0 allocation)
    l2 = next(
        line_alloc for line_alloc in res.lines if line_alloc.source_request_line_id == line_id2
    )
    assert l2.requested_quantity == Decimal("5.0")
    assert l2.allocated_quantity == Decimal("0")
    assert l2.remaining_quantity == Decimal("5.0")
