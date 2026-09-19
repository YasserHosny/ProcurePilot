from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from procurepilot_api.modules.orders.schemas import (
    DeliveryReceipt,
    EvidenceProjection,
    LifecycleLineSummary,
    LifecycleSummary,
    PurchaseOrder,
    SupplierConfirmation,
)


def validate_confirmation_against_order(
    order: PurchaseOrder, confirmation: SupplierConfirmation
) -> None:
    """Validate tenant/order/date/line relationships without performing I/O."""
    if confirmation.tenant_id != order.tenant_id:
        raise ValueError("confirmation tenant must match order tenant")
    if confirmation.purchase_order_id != order.id:
        raise ValueError("confirmation must belong to the order")
    if (
        confirmation.expected_delivery_date is not None
        and confirmation.expected_delivery_date < order.order_date
    ):
        raise ValueError("expected delivery date cannot precede order date")
    if confirmation.confirmed_at.date() < order.order_date:
        raise ValueError("confirmation timestamp cannot precede order date")
    line_ids = {line.id for line in order.lines}
    if any(line.purchase_order_line_id not in line_ids for line in confirmation.lines):
        raise ValueError("confirmation contains an unknown order line")
    for line in confirmation.lines:
        if line.confirmed_unit_price is not None:
            order_line = next(
                candidate
                for candidate in order.lines
                if candidate.id == line.purchase_order_line_id
            )
            if line.confirmed_unit_price.currency != order_line.unit_price.currency:
                raise ValueError("confirmation price currency must match order line currency")


def validate_receipt_against_order(order: PurchaseOrder, receipt: DeliveryReceipt) -> None:
    """Validate tenant/order/line relationships for one immutable receipt."""
    if receipt.tenant_id != order.tenant_id:
        raise ValueError("receipt tenant must match order tenant")
    if receipt.purchase_order_id != order.id:
        raise ValueError("receipt must belong to the order")
    if receipt.receipt_date < order.order_date:
        raise ValueError("receipt date cannot precede order date")
    line_ids = {line.id for line in order.lines}
    if any(line.purchase_order_line_id not in line_ids for line in receipt.lines):
        raise ValueError("receipt contains an unknown order line")


def build_lifecycle_summary(
    order: PurchaseOrder,
    confirmations: Iterable[SupplierConfirmation] = (),
    receipts: Iterable[DeliveryReceipt] = (),
) -> LifecycleSummary:
    """Build a deterministic evidence summary; absent evidence stays pending, not zero."""
    confirmation_list = tuple(confirmations)
    receipt_list = tuple(receipts)
    receipt_ids = [receipt.id for receipt in receipt_list]
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("lifecycle receipts must have unique identifiers")
    for confirmation in confirmation_list:
        validate_confirmation_against_order(order, confirmation)
    for receipt in receipt_list:
        validate_receipt_against_order(order, receipt)

    latest_confirmation = max(confirmation_list, key=lambda item: item.confirmed_at, default=None)
    confirmed_by_line: dict[UUID, Decimal] = {}
    if latest_confirmation is not None:
        confirmed_by_line = {
            line.purchase_order_line_id: line.confirmed_quantity
            for line in latest_confirmation.lines
        }
    received_by_line: defaultdict[UUID, Decimal] = defaultdict(Decimal)
    for receipt in receipt_list:
        for line in receipt.lines:
            received_by_line[line.purchase_order_line_id] += line.received_quantity

    summaries: list[LifecycleLineSummary] = []
    for order_line in order.lines:
        confirmed = (
            EvidenceProjection(
                state="available",
                quantity=confirmed_by_line[order_line.id],
                source_ids=(latest_confirmation.id,),
            )
            if latest_confirmation is not None and order_line.id in confirmed_by_line
            else EvidenceProjection(state="pending")
        )
        received = (
            EvidenceProjection(
                state="available",
                quantity=received_by_line[order_line.id],
                source_ids=tuple(
                    receipt.id
                    for receipt in receipt_list
                    if any(
                        line.purchase_order_line_id == order_line.id
                        for line in receipt.lines
                    )
                ),
            )
            if order_line.id in received_by_line
            else EvidenceProjection(state="pending")
        )
        received_quantity = received.quantity
        summaries.append(
            LifecycleLineSummary(
                purchase_order_line_id=order_line.id,
                ordered_quantity=order_line.ordered_quantity,
                confirmed=confirmed,
                received=received,
                remaining_quantity=(
                    max(order_line.ordered_quantity - received_quantity, Decimal("0"))
                    if received_quantity is not None
                    else None
                ),
                over_received_quantity=(
                    max(received_quantity - order_line.ordered_quantity, Decimal("0"))
                    if received_quantity is not None
                    else None
                ),
            )
        )

    confirmation_state = "available" if latest_confirmation is not None else "pending"
    receipt_state = "available" if receipt_list else "pending"
    status = order.status
    if order.status not in {"cancelled", "closed"} and receipt_list and all(
        summary.received.quantity is not None
        and summary.received.quantity >= summary.ordered_quantity
        for summary in summaries
    ):
        status = "received"
    elif order.status not in {"cancelled", "closed"} and receipt_list:
        status = "partially_received"
    return LifecycleSummary(
        purchase_order_id=order.id,
        status=status,
        confirmation=confirmation_state,
        receipt=receipt_state,
        lines=tuple(summaries),
    )
