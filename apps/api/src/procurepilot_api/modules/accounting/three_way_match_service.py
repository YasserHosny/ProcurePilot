"""Pure, deterministic order/receipt/bill comparison for R3.3.

This module deliberately has no persistence or provider dependencies.  Its projections are the
small, normalized boundary that a sync worker can later load from either internal evidence or an
accounting connector.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

EvidenceState = Literal["pending", "available", "unavailable"]
MatchResult = Literal["matched", "partial", "needs_review", "unmatched", "unavailable"]
DiscrepancyType = Literal[
    "missing_confirmation",
    "missing_receipt",
    "quantity_variance",
    "price_variance",
    "over_billed_quantity",
    "over_billed_price",
    "invoice_without_order",
    "ambiguous_order",
    "currency_mismatch",
]


def _decimal(value: Decimal | str | int) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("quantities, amounts, and tolerances must be finite")
    if result < 0:
        raise ValueError("quantities and amounts cannot be negative")
    return result


def _currency(value: str) -> str:
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("currency must be an uppercase ISO 4217 code")
    return value


def _text(value: str | None) -> str | None:
    return value.strip().casefold() if value is not None and value.strip() else None


@dataclass(frozen=True, slots=True)
class MatchMoney:
    amount: Decimal | str | int
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _decimal(self.amount))
        object.__setattr__(self, "currency", _currency(self.currency))


@dataclass(frozen=True, slots=True)
class OrderLineProjection:
    id: UUID | str
    line_number: int
    ordered_quantity: Decimal | str | int
    unit_price: MatchMoney
    product_id: UUID | str | None = None
    description: str = ""
    provider_line_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", UUID(str(self.id)))
        object.__setattr__(self, "ordered_quantity", _decimal(self.ordered_quantity))
        if self.line_number < 1:
            raise ValueError("order line number must be positive")


@dataclass(frozen=True, slots=True)
class EvidenceLineProjection:
    order_line_id: UUID | str
    quantity: Decimal | str | int
    unit_price: MatchMoney | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_line_id", UUID(str(self.order_line_id)))
        object.__setattr__(self, "quantity", _decimal(self.quantity))


@dataclass(frozen=True, slots=True)
class EvidenceProjection:
    state: EvidenceState
    source_ids: tuple[UUID | str, ...] = ()
    lines: tuple[EvidenceLineProjection, ...] = ()

    def __post_init__(self) -> None:
        ids = tuple(sorted(str(value) for value in self.source_ids))
        object.__setattr__(self, "source_ids", ids)
        if self.state == "available" and not ids:
            raise ValueError("available evidence requires source identifiers")
        if self.state == "available" and not self.lines:
            raise ValueError("available evidence requires at least one line")
        if self.state != "available" and self.lines:
            raise ValueError("pending or unavailable evidence cannot carry quantities")
        if self.state != "available" and ids:
            raise ValueError("pending or unavailable evidence cannot carry source identifiers")
        line_ids = [line.order_line_id for line in self.lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("evidence line identifiers must be unique")


@dataclass(frozen=True, slots=True)
class OrderProjection:
    id: UUID | str
    supplier_id: UUID | str
    currency: str
    order_date: date
    lines: tuple[OrderLineProjection, ...]
    order_number: str | None = None
    provider_order_reference: str | None = None
    provider_supplier_id: str | None = None
    document_references: tuple[str, ...] = ()
    confirmation: EvidenceProjection = EvidenceProjection("pending")
    receipt: EvidenceProjection = EvidenceProjection("pending")

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", UUID(str(self.id)))
        object.__setattr__(self, "supplier_id", UUID(str(self.supplier_id)))
        object.__setattr__(self, "currency", _currency(self.currency))
        if not self.lines:
            raise ValueError("an order must have at least one line")
        if any(line.unit_price.currency != self.currency for line in self.lines):
            raise ValueError("order line price currency must match order currency")


@dataclass(frozen=True, slots=True)
class InvoiceLineProjection:
    quantity: Decimal | str | int
    unit_price: MatchMoney
    description: str = ""
    product_id: UUID | str | None = None
    provider_line_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _decimal(self.quantity))


@dataclass(frozen=True, slots=True)
class RawBillProjection:
    provider_bill_id: str
    provider_vendor_id: str | None
    supplier_id: UUID | str | None
    bill_date: date
    total: MatchMoney
    lines: tuple[InvoiceLineProjection, ...]
    provider_order_reference: str | None = None
    document_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_bill_id.strip():
            raise ValueError("provider bill id is required")
        if not self.lines:
            raise ValueError("an invoice must have at least one line")
        if any(line.unit_price.currency != self.total.currency for line in self.lines):
            raise ValueError("invoice line price currency must match invoice total currency")
        if self.supplier_id is not None:
            object.__setattr__(self, "supplier_id", UUID(str(self.supplier_id)))


@dataclass(frozen=True, slots=True)
class ThreeWayToleranceRuleset:
    version: str
    quantity_tolerance: Decimal | str | int = Decimal("0")
    unit_price_tolerance: MatchMoney = MatchMoney(Decimal("0"), "USD")
    date_window_days: int = 14

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity_tolerance", _decimal(self.quantity_tolerance))
        if self.date_window_days < 0:
            raise ValueError("date window cannot be negative")
        if not self.version.strip():
            raise ValueError("ruleset version is required")


@dataclass(frozen=True, slots=True)
class MatchDiscrepancy:
    type: DiscrepancyType
    order_line_id: UUID | None = None
    evidence: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ThreeWayMatchResult:
    result: MatchResult
    order_id: UUID | None
    invoice_id: str
    ruleset_version: str
    discrepancies: tuple[MatchDiscrepancy, ...]
    source_ids: tuple[str, ...]
    source_hash: str


def _money_difference(left: MatchMoney, right: MatchMoney) -> Decimal | None:
    return None if left.currency != right.currency else left.amount - right.amount


def _same_identifier(left: UUID | str | None, right: UUID | str | None) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def _line_for_invoice(
    invoice_line: InvoiceLineProjection, order: OrderProjection
) -> OrderLineProjection | None:
    candidates = order.lines
    has_identifier = (
        bool(invoice_line.provider_line_reference) or invoice_line.product_id is not None
    )
    if invoice_line.provider_line_reference:
        candidates = tuple(
            line
            for line in candidates
            if _text(line.provider_line_reference) == _text(invoice_line.provider_line_reference)
        )
    elif invoice_line.product_id is not None:
        candidates = tuple(
            line
            for line in candidates
            if _same_identifier(line.product_id, invoice_line.product_id)
        )
    elif invoice_line.description:
        wanted = _text(invoice_line.description)
        candidates = tuple(line for line in candidates if _text(line.description) == wanted)
    if len(candidates) == 1:
        return candidates[0]
    if not has_identifier and not invoice_line.description and len(order.lines) == 1:
        return order.lines[0]
    return None


def _candidate_orders(
    invoice: RawBillProjection, orders: tuple[OrderProjection, ...], rules: ThreeWayToleranceRuleset
) -> tuple[OrderProjection, ...]:
    reference = _text(invoice.provider_order_reference)
    if reference:
        provider_referenced = tuple(
            order for order in orders if _text(order.provider_order_reference) == reference
        )
        if provider_referenced:
            same_currency = tuple(
                order for order in provider_referenced if order.currency == invoice.total.currency
            )
            return tuple(
                sorted(same_currency or provider_referenced, key=lambda order: str(order.id))
            )
        order_number_matches = tuple(
            order for order in orders if _text(order.order_number) == reference
        )
        if order_number_matches:
            same_currency = tuple(
                order for order in order_number_matches if order.currency == invoice.total.currency
            )
            return tuple(
                sorted(same_currency or order_number_matches, key=lambda order: str(order.id))
            )

    document_references = {_text(value) for value in invoice.document_references}
    candidates = []
    for order in orders:
        supplier_matches = (
            invoice.supplier_id is not None and order.supplier_id == invoice.supplier_id
        )
        provider_supplier_matches = invoice.provider_vendor_id is not None and _text(
            order.provider_supplier_id
        ) == _text(invoice.provider_vendor_id)
        if not (supplier_matches or provider_supplier_matches):
            continue
        if abs((order.order_date - invoice.bill_date).days) > rules.date_window_days:
            continue
        if document_references and not document_references.intersection(
            {
                _text(order.order_number),
                _text(order.provider_order_reference),
                *map(_text, order.document_references),
            }
        ):
            continue
        candidates.append(order)
    same_currency = [order for order in candidates if order.currency == invoice.total.currency]
    return tuple(sorted(same_currency or candidates, key=lambda order: str(order.id)))


def _money_payload(value: MatchMoney) -> dict[str, str]:
    return {"amount": format(value.amount.normalize(), "f"), "currency": value.currency}


def _line_payload(
    line: OrderLineProjection | InvoiceLineProjection | EvidenceLineProjection,
) -> dict[str, object]:
    if isinstance(line, OrderLineProjection):
        return {
            "id": str(line.id),
            "line_number": line.line_number,
            "ordered_quantity": format(line.ordered_quantity.normalize(), "f"),
            "unit_price": _money_payload(line.unit_price),
            "product_id": str(line.product_id) if line.product_id is not None else None,
            "description": _text(line.description),
            "provider_line_reference": _text(line.provider_line_reference),
        }
    if isinstance(line, InvoiceLineProjection):
        return {
            "quantity": format(line.quantity.normalize(), "f"),
            "unit_price": _money_payload(line.unit_price),
            "product_id": str(line.product_id) if line.product_id is not None else None,
            "description": _text(line.description),
            "provider_line_reference": _text(line.provider_line_reference),
        }
    return {
        "order_line_id": str(line.order_line_id),
        "quantity": format(line.quantity.normalize(), "f"),
        "unit_price": _money_payload(line.unit_price) if line.unit_price else None,
    }


def _evidence_payload(evidence: EvidenceProjection) -> dict[str, object]:
    return {
        "state": evidence.state,
        "source_ids": evidence.source_ids,
        "lines": [_line_payload(line) for line in evidence.lines],
    }


def _order_payload(order: OrderProjection) -> dict[str, object]:
    return {
        "id": str(order.id),
        "supplier_id": str(order.supplier_id),
        "currency": order.currency,
        "order_date": order.order_date.isoformat(),
        "order_number": _text(order.order_number),
        "provider_order_reference": _text(order.provider_order_reference),
        "provider_supplier_id": _text(order.provider_supplier_id),
        "document_references": tuple(sorted(_text(value) for value in order.document_references)),
        "lines": [_line_payload(line) for line in order.lines],
        "confirmation": _evidence_payload(order.confirmation),
        "receipt": _evidence_payload(order.receipt),
    }


def _source_payload(
    invoice: RawBillProjection,
    candidates: tuple[OrderProjection, ...],
    rules: ThreeWayToleranceRuleset,
) -> dict[str, object]:
    return {
        "rules": {
            "version": rules.version,
            "quantity_tolerance": format(rules.quantity_tolerance.normalize(), "f"),
            "unit_price_tolerance": _money_payload(rules.unit_price_tolerance),
            "date_window_days": rules.date_window_days,
        },
        "invoice": {
            "provider_bill_id": invoice.provider_bill_id,
            "provider_vendor_id": _text(invoice.provider_vendor_id),
            "supplier_id": str(invoice.supplier_id) if invoice.supplier_id else None,
            "bill_date": invoice.bill_date.isoformat(),
            "total": _money_payload(invoice.total),
            "provider_order_reference": _text(invoice.provider_order_reference),
            "document_references": tuple(
                sorted(_text(value) for value in invoice.document_references)
            ),
            "lines": [_line_payload(line) for line in invoice.lines],
        },
        "candidate_orders": [_order_payload(order) for order in candidates],
    }


def _canonical(result: ThreeWayMatchResult, source_payload: dict[str, object]) -> bytes:
    payload = {
        "result": result.result,
        "order_id": str(result.order_id) if result.order_id else None,
        "invoice_id": result.invoice_id,
        "ruleset_version": result.ruleset_version,
        "source_ids": result.source_ids,
        "discrepancies": [
            {
                "type": item.type,
                "order_line_id": str(item.order_line_id) if item.order_line_id else None,
                "evidence": item.evidence,
            }
            for item in result.discrepancies
        ],
        "sources": source_payload,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _hashed(result: ThreeWayMatchResult, source_payload: dict[str, object]) -> ThreeWayMatchResult:
    return ThreeWayMatchResult(
        result=result.result,
        order_id=result.order_id,
        invoice_id=result.invoice_id,
        ruleset_version=result.ruleset_version,
        discrepancies=result.discrepancies,
        source_ids=result.source_ids,
        source_hash=hashlib.sha256(_canonical(result, source_payload)).hexdigest(),
    )


def evaluate_three_way_match(
    invoice: RawBillProjection,
    orders: tuple[OrderProjection, ...] | list[OrderProjection],
    ruleset: ThreeWayToleranceRuleset,
) -> ThreeWayMatchResult:
    """Evaluate one normalized bill without I/O; repeated calls produce the same hash."""
    candidates = _candidate_orders(invoice, tuple(orders), ruleset)
    source_payload = _source_payload(invoice, candidates, ruleset)
    discrepancies: list[MatchDiscrepancy] = []
    selected: OrderProjection | None = None
    if len(candidates) == 1:
        selected = candidates[0]
    elif len(candidates) == 0:
        discrepancies.append(MatchDiscrepancy("invoice_without_order"))
    else:
        discrepancies.append(MatchDiscrepancy("ambiguous_order"))

    if selected is None:
        outcome: MatchResult = "unmatched"
        if discrepancies[0].type == "ambiguous_order":
            outcome = "needs_review"
        provisional = ThreeWayMatchResult(
            outcome,
            None,
            invoice.provider_bill_id,
            ruleset.version,
            tuple(discrepancies),
            (invoice.provider_bill_id,),
            "",
        )
        return _hashed(provisional, source_payload)

    if selected.currency != invoice.total.currency:
        discrepancies.append(
            MatchDiscrepancy(
                "currency_mismatch",
                evidence=(
                    ("order_currency", selected.currency),
                    ("invoice_currency", invoice.total.currency),
                ),
            )
        )

    if selected.confirmation.state == "unavailable":
        outcome = "unavailable"
    else:
        outcome = "partial"
    if selected.confirmation.state != "available":
        discrepancies.append(MatchDiscrepancy("missing_confirmation"))
    if selected.receipt.state == "unavailable":
        outcome = "unavailable"
    if selected.receipt.state != "available":
        discrepancies.append(MatchDiscrepancy("missing_receipt"))

    receipt_by_line = {line.order_line_id: line for line in selected.receipt.lines}
    confirmation_by_line = {line.order_line_id: line for line in selected.confirmation.lines}
    assigned_order_lines: set[UUID] = set()
    for invoice_line in invoice.lines:
        order_line = _line_for_invoice(invoice_line, selected)
        if order_line is None:
            discrepancies.append(MatchDiscrepancy("quantity_variance"))
            continue
        if order_line.id in assigned_order_lines:
            discrepancies.append(MatchDiscrepancy("quantity_variance", order_line.id))
            continue
        assigned_order_lines.add(order_line.id)
        received = receipt_by_line.get(order_line.id)
        confirmed = confirmation_by_line.get(order_line.id)
        if selected.receipt.state == "available" and received is None:
            discrepancies.append(MatchDiscrepancy("missing_receipt", order_line.id))
        if selected.confirmation.state == "available" and confirmed is None:
            discrepancies.append(MatchDiscrepancy("missing_confirmation", order_line.id))
        if (
            received is not None
            and invoice_line.quantity > received.quantity + ruleset.quantity_tolerance
        ):
            discrepancies.append(
                MatchDiscrepancy(
                    "over_billed_quantity",
                    order_line.id,
                    (
                        ("received", str(received.quantity)),
                        ("invoiced", str(invoice_line.quantity)),
                    ),
                )
            )
        elif (
            received is not None
            and abs(invoice_line.quantity - received.quantity) > ruleset.quantity_tolerance
        ):
            discrepancies.append(MatchDiscrepancy("quantity_variance", order_line.id))
        if invoice_line.quantity > order_line.ordered_quantity + ruleset.quantity_tolerance:
            discrepancies.append(MatchDiscrepancy("over_billed_quantity", order_line.id))

        for compared_quantity, evidence_quantity in (
            (invoice_line.quantity, confirmed.quantity if confirmed else None),
        ):
            if evidence_quantity is None:
                continue
            difference = compared_quantity - evidence_quantity
            if abs(difference) > ruleset.quantity_tolerance:
                discrepancy_type: DiscrepancyType = (
                    "over_billed_quantity" if difference > 0 else "quantity_variance"
                )
                discrepancies.append(MatchDiscrepancy(discrepancy_type, order_line.id))

        price_difference = _money_difference(order_line.unit_price, invoice_line.unit_price)
        if price_difference is None:
            discrepancies.append(
                MatchDiscrepancy(
                    "currency_mismatch",
                    order_line.id,
                    (
                        ("order_currency", order_line.unit_price.currency),
                        ("invoice_currency", invoice_line.unit_price.currency),
                    ),
                )
            )
        elif ruleset.unit_price_tolerance.currency != invoice_line.unit_price.currency:
            discrepancies.append(
                MatchDiscrepancy(
                    "currency_mismatch",
                    order_line.id,
                    (
                        ("tolerance_currency", ruleset.unit_price_tolerance.currency),
                        ("invoice_currency", invoice_line.unit_price.currency),
                    ),
                )
            )
        elif abs(price_difference) > ruleset.unit_price_tolerance.amount:
            discrepancy_type: DiscrepancyType = (
                "over_billed_price" if price_difference < 0 else "price_variance"
            )
            discrepancies.append(MatchDiscrepancy(discrepancy_type, order_line.id))
        if confirmed is not None and confirmed.unit_price is not None:
            confirmation_difference = _money_difference(
                invoice_line.unit_price, confirmed.unit_price
            )
            if confirmation_difference is None:
                discrepancies.append(MatchDiscrepancy("currency_mismatch", order_line.id))
            elif ruleset.unit_price_tolerance.currency != confirmed.unit_price.currency:
                discrepancies.append(
                    MatchDiscrepancy(
                        "currency_mismatch",
                        order_line.id,
                        (("tolerance_currency", ruleset.unit_price_tolerance.currency),),
                    )
                )
            elif abs(confirmation_difference) > ruleset.unit_price_tolerance.amount:
                discrepancy_type = (
                    "over_billed_price" if confirmation_difference < 0 else "price_variance"
                )
                discrepancies.append(MatchDiscrepancy(discrepancy_type, order_line.id))

    discrepancies = sorted(
        set(discrepancies), key=lambda item: (item.type, str(item.order_line_id), item.evidence)
    )
    if outcome == "unavailable":
        pass
    elif (
        any(item.type == "currency_mismatch" for item in discrepancies)
        or (
            selected.confirmation.state == "available"
            and any(item.type == "missing_confirmation" for item in discrepancies)
        )
        or (
            selected.receipt.state == "available"
            and any(item.type == "missing_receipt" for item in discrepancies)
        )
    ):
        outcome = "needs_review"
    elif discrepancies and any(
        item.type
        in {"over_billed_quantity", "over_billed_price", "quantity_variance", "price_variance"}
        for item in discrepancies
    ):
        outcome = "needs_review"
    elif selected.confirmation.state == "available" and selected.receipt.state == "available":
        outcome = "matched"
    source_ids = tuple(
        sorted(
            {
                invoice.provider_bill_id,
                *selected.confirmation.source_ids,
                *selected.receipt.source_ids,
            }
        )
    )
    provisional = ThreeWayMatchResult(
        outcome,
        selected.id,
        invoice.provider_bill_id,
        ruleset.version,
        tuple(discrepancies),
        source_ids,
        "",
    )
    return _hashed(provisional, source_payload)


match_three_way = evaluate_three_way_match

__all__ = [
    "EvidenceLineProjection",
    "EvidenceProjection",
    "InvoiceLineProjection",
    "MatchDiscrepancy",
    "MatchMoney",
    "OrderLineProjection",
    "OrderProjection",
    "RawBillProjection",
    "ThreeWayMatchResult",
    "ThreeWayToleranceRuleset",
    "evaluate_three_way_match",
    "match_three_way",
]
