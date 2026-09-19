from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.accounting import three_way_sync_service as sync_module
from procurepilot_api.modules.accounting.three_way_sync_service import (
    ThreeWaySyncService,
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONNECTION = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BILL = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SUPPLIER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
ORDER = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
ORDER_LINE = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
RECEIPT_1 = UUID("00000000-0000-0000-0000-000000000001")
RECEIPT_2 = UUID("00000000-0000-0000-0000-000000000002")


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.rows: list[dict[str, object]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: dict[str, object]) -> None:
        self.connection.queries.append((query, params))
        lowered = query.lower()
        if "from synced_bill b" in lowered:
            self.rows = [
                {
                    "id": BILL,
                    "provider_bill_id": "bill-1",
                    "vendor_id": uuid4(),
                    "matched_supplier_id": SUPPLIER,
                    "amount": Decimal("20"),
                    "currency": "GBP",
                    "bill_date": date(2026, 9, 20),
                    "provider_order_reference": "PO-1",
                    "document_references": [],
                    "provider_vendor_id": "vendor-1",
                }
            ]
        elif "from synced_bill_line" in lowered:
            self.rows = [
                {
                    "id": uuid4(),
                    "line_number": 1,
                    "provider_line_reference": None,
                    "provider_product_reference": None,
                    "description": "Widget",
                    "quantity": Decimal("2"),
                    "unit_price_amount": Decimal("10"),
                    "unit_price_currency": "GBP",
                }
            ] if self.connection.with_lines else []
        elif "from purchase_order\n" in lowered:
            self.rows = [
                {
                    "id": ORDER,
                    "order_number": "PO-1",
                    "supplier_id": SUPPLIER,
                    "order_date": date(2026, 9, 19),
                    "total_currency": "GBP",
                    "source_reference": "internal:po-1",
                }
            ]
        elif "from purchase_order_line" in lowered:
            self.rows = [
                {
                    "id": ORDER_LINE,
                    "line_number": 1,
                    "workspace_product_id": None,
                    "description": "Widget",
                    "ordered_quantity": Decimal("2"),
                    "unit_price_amount": Decimal("10"),
                    "unit_price_currency": "GBP",
                }
            ]
        elif "from supplier_confirmation_line" in lowered:
            self.rows = [
                {
                    "purchase_order_line_id": ORDER_LINE,
                    "confirmed_quantity": Decimal("2"),
                    "confirmed_unit_price_amount": Decimal("10"),
                    "confirmed_unit_price_currency": "GBP",
                }
            ]
        elif "from supplier_confirmation" in lowered:
            self.rows = [{"id": uuid4()}] if self.connection.with_confirmation else []
        elif "from delivery_receipt r" in lowered:
            self.rows = [
                {
                    "id": RECEIPT_1,
                    "purchase_order_line_id": ORDER_LINE,
                    "received_quantity": Decimal("1"),
                },
                {
                    "id": RECEIPT_2,
                    "purchase_order_line_id": ORDER_LINE,
                    "received_quantity": Decimal("1"),
                },
            ]
        else:
            self.rows = []

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, *, with_lines: bool = True, with_confirmation: bool = False) -> None:
        self.with_lines = with_lines
        self.with_confirmation = with_confirmation
        self.queries: list[tuple[str, dict[str, object]]] = []

    def cursor(self, **_kwargs: object) -> FakeCursor:
        return FakeCursor(self)


def test_evaluates_and_persists_exact_match_with_cumulative_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(with_confirmation=True)
    persisted: list[dict[str, object]] = []

    def persist(*args: object, **kwargs: object) -> None:
        persisted.append(kwargs)

    monkeypatch.setattr(sync_module, "persist_three_way_match", persist)

    summary = ThreeWaySyncService().run(
        connection, tenant_id=TENANT, connection_id=CONNECTION
    )

    assert summary.evaluated == 1
    assert summary.matched == 1
    assert summary.discrepancies == 0
    assert persisted[0]["purchase_order_id"] == ORDER
    evidence = persisted[0]["evidence"]
    assert evidence["received_quantity"] == "2"
    assert all(params["tenant_id"] == TENANT for _query, params in connection.queries)
    assert all(
        isinstance(source_id, str)
        for section in (evidence["confirmation"], evidence["receipt"])
        for source_id in section["source_ids"]
    )


def test_missing_confirmation_preserves_pending_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(
        sync_module,
        "persist_three_way_match",
        lambda *args, **kwargs: persisted.append(kwargs),
    )

    summary = ThreeWaySyncService().run(
        connection, tenant_id=TENANT, connection_id=CONNECTION
    )

    assert summary.needs_review == 1
    assert persisted[0]["evidence"]["confirmed_quantity"] is None
    assert persisted[0]["evidence"]["confirmation"]["state"] == "pending"


def test_bill_without_normalized_lines_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(with_lines=False)
    monkeypatch.setattr(sync_module, "persist_three_way_match", lambda *args, **kwargs: None)

    summary = ThreeWaySyncService().run(
        connection, tenant_id=TENANT, connection_id=CONNECTION
    )

    assert summary.evaluated == 0
    assert summary.skipped_without_lines == 1
    assert not any("from purchase_order" in query.lower() for query, _params in connection.queries)


def test_no_selected_order_persists_bill_relationship_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(
        sync_module,
        "persist_three_way_match",
        lambda *args, **kwargs: persisted.append(kwargs),
    )
    monkeypatch.setattr(
        sync_module,
        "evaluate_three_way_match",
        lambda *_args, **_kwargs: sync_module.ThreeWayMatchResult(
            "unmatched", None, "bill-1", "three-way-v1", (), ("bill-1",), "hash"
        ),
    )

    ThreeWaySyncService().run(connection, tenant_id=TENANT, connection_id=CONNECTION)

    assert persisted[0]["synced_bill_id"] == BILL
    assert persisted[0]["purchase_order_id"] is None
    assert persisted[0]["delivery_receipt_id"] is None
