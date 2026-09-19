from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.orders.schemas import (
    DeliveryReceipt,
    DeliveryReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierConfirmation,
    SupplierConfirmationLine,
)
from procurepilot_api.modules.orders.validation import build_lifecycle_summary

TENANT = UUID("00000000-0000-0000-0000-000000000001")
SUPPLIER = UUID("00000000-0000-0000-0000-000000000002")
MEMBER = UUID("00000000-0000-0000-0000-000000000003")
ORDER = UUID("00000000-0000-0000-0000-000000000004")
LINE_ONE = UUID("00000000-0000-0000-0000-000000000005")
LINE_TWO = UUID("00000000-0000-0000-0000-000000000006")


def _line(line_id: UUID, number: int, quantity: str, total: str) -> PurchaseOrderLine:
    return PurchaseOrderLine(
        id=line_id,
        line_number=number,
        description=f"Item {number}",
        ordered_quantity=Decimal(quantity),
        base_unit="each",
        unit_price={"amount": Decimal("10"), "currency": "GBP"},
        tax={"amount": Decimal("0"), "currency": "GBP"},
        line_total={"amount": Decimal(total), "currency": "GBP"},
    )


def _order(
    lines: tuple[PurchaseOrderLine, ...] = (), status: str = "submitted"
) -> PurchaseOrder:
    actual_lines = lines or (_line(LINE_ONE, 1, "2", "20"), _line(LINE_TWO, 2, "3", "30"))
    total_amount = sum((line.line_total.amount for line in actual_lines), Decimal("0"))
    return PurchaseOrder(
        id=ORDER,
        tenant_id=TENANT,
        order_number="PO-100",
        supplier_id=SUPPLIER,
        status=status,
        order_date=date(2026, 9, 19),
        expected_delivery_date=date(2026, 9, 25),
        total={"amount": total_amount, "currency": "GBP"},
        tax={"amount": Decimal("0"), "currency": "GBP"},
        source_kind="manual",
        source_reference="manual:PO-100",
        created_by=MEMBER,
        created_at=datetime(2026, 9, 19, tzinfo=UTC),
        updated_at=datetime(2026, 9, 19, tzinfo=UTC),
        lines=actual_lines,
    )


def test_valid_two_line_order() -> None:
    order = _order()
    assert len(order.lines) == 2
    assert order.total.currency == "GBP"


@pytest.mark.parametrize(
    ("total", "tax"),
    [
        ({"amount": "50", "currency": "USD"}, {"amount": "0", "currency": "GBP"}),
        ({"amount": "50", "currency": "GBP"}, {"amount": "1", "currency": "USD"}),
    ],
)
def test_invalid_money_currency_pairs(total: dict[str, str], tax: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _order()
        PurchaseOrder(
            **_order().model_dump(exclude={"total", "tax"}), total=total, tax=tax
        )


@pytest.mark.parametrize("quantity", ["-1", "-0.001"])
def test_negative_quantities_are_rejected(quantity: str) -> None:
    with pytest.raises(ValidationError):
        _line(LINE_ONE, 1, quantity, "20")


def test_zero_quantity_is_valid_but_missing_receipt_is_pending() -> None:
    line = _line(LINE_ONE, 1, "0", "0")
    order = _order((line,))
    summary = build_lifecycle_summary(order)
    assert summary.lines[0].ordered_quantity == Decimal("0")
    assert summary.lines[0].received.state == "pending"
    assert summary.lines[0].received.quantity is None


def test_partial_receipt_summary_accumulates_receipts() -> None:
    order = _order()
    receipt_one = DeliveryReceipt(
        id=UUID("00000000-0000-0000-0000-000000000007"),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-1",
        receipt_date=date(2026, 9, 22),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="manual:GRN-1",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        lines=(
            DeliveryReceiptLine(
                id=UUID(int=8),
                purchase_order_line_id=LINE_ONE,
                received_quantity=Decimal("1"),
            ),
        ),
    )
    receipt_two = receipt_one.model_copy(
        update={
            "id": UUID("00000000-0000-0000-0000-000000000009"),
            "receipt_reference": "GRN-2",
            "lines": (
                DeliveryReceiptLine(
                    id=UUID(int=10),
                    purchase_order_line_id=LINE_ONE,
                    received_quantity=Decimal("0.5"),
                ),
            ),
        }
    )
    summary = build_lifecycle_summary(order, receipts=(receipt_one, receipt_two))
    line_summary = summary.lines[0]
    assert summary.status == "partially_received"
    assert line_summary.received.quantity == Decimal("1.5")
    assert line_summary.received.source_ids == (
        receipt_one.id,
        receipt_two.id,
    )
    assert line_summary.remaining_quantity == Decimal("0.5")
    assert line_summary.over_received_quantity == Decimal("0")


def test_missing_confirmation_and_receipt_are_pending_evidence() -> None:
    summary = build_lifecycle_summary(_order())
    assert summary.confirmation == "pending"
    assert summary.receipt == "pending"
    assert summary.lines[0].confirmed.quantity is None
    assert summary.lines[0].received.quantity is None


def test_confirmation_line_price_must_match_order_currency() -> None:
    confirmation = SupplierConfirmation(
        id=UUID(int=11),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        supplier_reference="SUP-1",
        confirmed_at=datetime(2026, 9, 20, tzinfo=UTC),
        source_kind="manual",
        source_reference="manual:SUP-1",
        recorded_by=MEMBER,
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        lines=(
            SupplierConfirmationLine(
                id=UUID(int=12),
                purchase_order_line_id=LINE_ONE,
                confirmed_quantity=Decimal("2"),
                confirmed_unit_price={"amount": Decimal("10"), "currency": "USD"},
            ),
        ),
    )
    with pytest.raises(ValueError, match="currency"):
        build_lifecycle_summary(_order(), confirmations=(confirmation,))


def test_confirmation_summary_preserves_confirmation_source_id() -> None:
    confirmation = SupplierConfirmation(
        id=UUID(int=23),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        supplier_reference="SUP-VALID",
        confirmed_at=datetime(2026, 9, 20, tzinfo=UTC),
        source_kind="manual",
        source_reference="manual:SUP-VALID",
        recorded_by=MEMBER,
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        lines=(
            SupplierConfirmationLine(
                id=UUID(int=24),
                purchase_order_line_id=LINE_ONE,
                confirmed_quantity=Decimal("2"),
            ),
        ),
    )
    summary = build_lifecycle_summary(_order(), confirmations=(confirmation,))
    assert summary.lines[0].confirmed.source_ids == (confirmation.id,)


def test_over_receipt_has_non_negative_remaining_and_explicit_variance() -> None:
    order = _order((_line(LINE_ONE, 1, "2", "20"),))
    receipt = DeliveryReceipt(
        id=UUID(int=13),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-OVER",
        receipt_date=date(2026, 9, 22),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="manual:GRN-OVER",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        lines=(
            DeliveryReceiptLine(
                id=UUID(int=14),
                purchase_order_line_id=LINE_ONE,
                received_quantity=Decimal("3"),
            ),
        ),
    )
    line = build_lifecycle_summary(order, receipts=(receipt,)).lines[0]
    assert line.remaining_quantity == Decimal("0")
    assert line.over_received_quantity == Decimal("1")


def test_duplicate_receipt_ids_are_rejected() -> None:
    receipt = DeliveryReceipt(
        id=UUID(int=15),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-DUP",
        receipt_date=date(2026, 9, 22),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="manual:GRN-DUP",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        lines=(
            DeliveryReceiptLine(
                id=UUID(int=16),
                purchase_order_line_id=LINE_ONE,
                received_quantity=Decimal("1"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="unique identifiers"):
        build_lifecycle_summary(_order(), receipts=(receipt, receipt))


@pytest.mark.parametrize("status", ["cancelled", "closed"])
def test_terminal_order_status_is_preserved_with_receipt_evidence(status: str) -> None:
    receipt = DeliveryReceipt(
        id=UUID(int=17),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-TERMINAL",
        receipt_date=date(2026, 9, 22),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="manual:GRN-TERMINAL",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        lines=(
            DeliveryReceiptLine(
                id=UUID(int=18),
                purchase_order_line_id=LINE_ONE,
                received_quantity=Decimal("2"),
            ),
        ),
    )
    assert build_lifecycle_summary(_order(status=status), receipts=(receipt,)).status == status


def test_confirmation_and_receipt_cannot_precede_order_date() -> None:
    confirmation = SupplierConfirmation(
        id=UUID(int=19),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        supplier_reference="SUP-EARLY",
        confirmed_at=datetime(2026, 9, 18, tzinfo=UTC),
        source_kind="manual",
        source_reference="manual:SUP-EARLY",
        recorded_by=MEMBER,
        created_at=datetime(2026, 9, 19, tzinfo=UTC),
        lines=(
            SupplierConfirmationLine(
                id=UUID(int=20),
                purchase_order_line_id=LINE_ONE,
                confirmed_quantity=Decimal("2"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="confirmation timestamp"):
        build_lifecycle_summary(_order(), confirmations=(confirmation,))

    receipt = DeliveryReceipt(
        id=UUID(int=21),
        tenant_id=TENANT,
        purchase_order_id=ORDER,
        receipt_reference="GRN-EARLY",
        receipt_date=date(2026, 9, 18),
        received_by=MEMBER,
        source_kind="manual",
        source_reference="manual:GRN-EARLY",
        created_at=datetime(2026, 9, 19, tzinfo=UTC),
        lines=(
            DeliveryReceiptLine(
                id=UUID(int=22),
                purchase_order_line_id=LINE_ONE,
                received_quantity=Decimal("1"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="receipt date"):
        build_lifecycle_summary(_order(), receipts=(receipt,))


def test_datetime_fields_require_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        PurchaseOrder(
            **_order().model_dump(exclude={"created_at"}),
            created_at=datetime(2026, 9, 19),
        )


def test_boundary_rejects_whitespace_business_strings() -> None:
    with pytest.raises((ValidationError, ValueError)):
        PurchaseOrderLine(
            **_line(LINE_ONE, 1, "2", "20").model_dump(exclude={"description"}),
            description="   ",
        )


def test_boundary_rejects_boolean_coercions() -> None:
    with pytest.raises((ValidationError, ValueError)):
        PurchaseOrderLine(
            **_line(LINE_ONE, 1, "2", "20").model_dump(exclude={"ordered_quantity"}),
            ordered_quantity=True,
        )
