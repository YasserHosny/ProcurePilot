"""Database integration for evaluating normalized accounting bills against internal orders."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .three_way_match_persistence import persist_three_way_match
from .three_way_match_service import (
    EvidenceLineProjection,
    EvidenceProjection,
    InvoiceLineProjection,
    MatchMoney,
    OrderLineProjection,
    OrderProjection,
    RawBillProjection,
    ThreeWayMatchResult,
    ThreeWayToleranceRuleset,
    evaluate_three_way_match,
)

THREE_WAY_RULESET_VERSION = "three-way-v1"
THREE_WAY_RULESET = ThreeWayToleranceRuleset(
    THREE_WAY_RULESET_VERSION,
    quantity_tolerance=Decimal("0"),
    unit_price_tolerance=MatchMoney(Decimal("0.01"), "USD"),
)


@dataclass(frozen=True, slots=True)
class ThreeWaySyncSummary:
    evaluated: int = 0
    skipped_without_lines: int = 0
    matched: int = 0
    needs_review: int = 0
    unmatched: int = 0
    unavailable: int = 0
    discrepancies: int = 0

    def add(self, result: ThreeWayMatchResult) -> ThreeWaySyncSummary:
        return ThreeWaySyncSummary(
            evaluated=self.evaluated + 1,
            skipped_without_lines=self.skipped_without_lines,
            matched=self.matched + int(result.result == "matched"),
            needs_review=self.needs_review + int(result.result in {"needs_review", "partial"}),
            unmatched=self.unmatched + int(result.result == "unmatched"),
            unavailable=self.unavailable + int(result.result == "unavailable"),
            discrepancies=self.discrepancies + len(result.discrepancies),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "evaluated": self.evaluated,
            "skipped_without_lines": self.skipped_without_lines,
            "matched": self.matched,
            "needs_review": self.needs_review,
            "unmatched": self.unmatched,
            "unavailable": self.unavailable,
            "discrepancies": self.discrepancies,
        }


def _value(row: object, key: str, position: int | None = None) -> object:
    if isinstance(row, dict):
        return row[key]
    if position is None:
        raise KeyError(key)
    return row[position]


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _money(amount: object, currency: object) -> MatchMoney:
    return MatchMoney(Decimal(str(amount)), str(currency).upper())


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _document_references(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if str(item).strip())


def _evidence(
    rows: list[Any],
    *,
    quantity_key: str,
    price_amount_key: str | None = None,
    price_currency_key: str | None = None,
    source_ids: tuple[UUID | str, ...] = (),
) -> EvidenceProjection:
    if not rows:
        return EvidenceProjection("pending")
    lines: list[EvidenceLineProjection] = []
    for row in rows:
        price = None
        if price_amount_key and _value(row, price_amount_key) is not None:
            price = _money(_value(row, price_amount_key), _value(row, price_currency_key))
        lines.append(
            EvidenceLineProjection(
                _value(row, "purchase_order_line_id"), _value(row, quantity_key), price
            )
        )
    return EvidenceProjection(
        "available",
        tuple(source_ids),
        tuple(lines),
    )


def _evidence_payload(
    bill: RawBillProjection, order: OrderProjection | None, result: ThreeWayMatchResult
) -> dict[str, object]:
    payload: dict[str, object] = {
        "invoiced_quantity": format(sum((line.quantity for line in bill.lines), Decimal("0")), "f"),
        "invoiced_total_amount": format(bill.total.amount, "f"),
        "invoiced_total_currency": bill.total.currency,
        "invoiced_lines": [
            {
                "quantity": format(line.quantity, "f"),
                "unit_price_amount": format(line.unit_price.amount, "f"),
                "unit_price_currency": line.unit_price.currency,
                "description": line.description,
                "provider_line_reference": line.provider_line_reference,
            }
            for line in bill.lines
        ],
    }
    if order is not None:
        payload.update(
            {
                "ordered_quantity": format(
                    sum((line.ordered_quantity for line in order.lines), Decimal("0")), "f"
                ),
                "ordered_unit_price_amount": format(order.lines[0].unit_price.amount, "f"),
                "ordered_unit_price_currency": order.currency,
                "ordered_total_amount": format(
                    sum(
                        (line.ordered_quantity * line.unit_price.amount for line in order.lines),
                        Decimal("0"),
                    ),
                    "f",
                ),
                "ordered_total_currency": order.currency,
                "confirmed_quantity": _evidence_quantity(order.confirmation),
                "received_quantity": _evidence_quantity(order.receipt),
                "confirmation": _projection_evidence(order.confirmation),
                "receipt": _projection_evidence(order.receipt),
            }
        )
    payload["result"] = result.result
    return payload


def _evidence_quantity(evidence: EvidenceProjection) -> str | None:
    if evidence.state != "available":
        return None
    return format(sum((line.quantity for line in evidence.lines), Decimal("0")), "f")


def _projection_evidence(evidence: EvidenceProjection) -> dict[str, object]:
    return {
        "state": evidence.state,
        "source_ids": [str(source_id) for source_id in evidence.source_ids],
        "lines": [
            {"order_line_id": str(line.order_line_id), "quantity": format(line.quantity, "f")}
            for line in evidence.lines
        ],
    }


def _load_bills(
    conn: psycopg.Connection[Any], tenant_id: UUID, connection_id: UUID
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.id, b.provider_bill_id, b.vendor_id, b.matched_supplier_id,
                   b.amount, b.currency, b.bill_date, b.provider_order_reference,
                   b.document_references, v.provider_vendor_id
            FROM synced_bill b
            JOIN synced_vendor v ON v.tenant_id = b.tenant_id AND v.id = b.vendor_id
            WHERE b.tenant_id = %(tenant_id)s AND b.connection_id = %(connection_id)s
              AND v.tenant_id = %(tenant_id)s
            ORDER BY b.id
            """,
            {"tenant_id": tenant_id, "connection_id": connection_id},
        )
        bills = [dict(row) for row in cur.fetchall()]
        for bill in bills:
            cur.execute(
                """
                SELECT id, line_number, provider_line_reference, provider_product_reference,
                       description, quantity, unit_price_amount, unit_price_currency
                FROM synced_bill_line
                WHERE tenant_id = %(tenant_id)s AND synced_bill_id = %(synced_bill_id)s
                ORDER BY line_number
                """,
                {"tenant_id": tenant_id, "synced_bill_id": bill["id"]},
            )
            bill["lines"] = list(cur.fetchall())
        return bills


class ThreeWaySyncService:
    """Load evidence, evaluate bills, and persist in the caller's transaction."""

    def __init__(self, ruleset: ThreeWayToleranceRuleset = THREE_WAY_RULESET) -> None:
        self.ruleset = ruleset

    def run(
        self, conn: psycopg.Connection[Any], tenant_id: UUID, connection_id: UUID
    ) -> ThreeWaySyncSummary:
        summary = ThreeWaySyncSummary()
        for bill_row in _load_bills(conn, tenant_id, connection_id):
            lines = bill_row["lines"]
            if not lines:
                summary = ThreeWaySyncSummary(
                    **{
                        **summary.as_dict(),
                        "skipped_without_lines": summary.skipped_without_lines + 1,
                    }
                )
                continue
            bill = RawBillProjection(
                provider_bill_id=str(bill_row["provider_bill_id"]),
                provider_vendor_id=str(bill_row["provider_vendor_id"]),
                supplier_id=_uuid(bill_row["matched_supplier_id"])
                if bill_row["matched_supplier_id"]
                else None,
                bill_date=_as_date(bill_row["bill_date"]),
                total=_money(bill_row["amount"], bill_row["currency"]),
                provider_order_reference=bill_row.get("provider_order_reference"),
                document_references=_document_references(bill_row.get("document_references")),
                lines=tuple(
                    InvoiceLineProjection(
                        line["quantity"],
                        _money(line["unit_price_amount"], line["unit_price_currency"]),
                        description=line["description"],
                        # Provider line identifiers are evidence only; they are not internal
                        # purchase_order_line IDs and must not block description matching.
                        provider_line_reference=None,
                    )
                    for line in lines
                ),
            )
            orders = self._load_orders(conn, tenant_id, bill)
            ruleset = replace(
                self.ruleset,
                unit_price_tolerance=MatchMoney(
                    self.ruleset.unit_price_tolerance.amount, bill.total.currency
                ),
            )
            result = evaluate_three_way_match(bill, orders, ruleset)
            selected_order = next((order for order in orders if order.id == result.order_id), None)
            persist_three_way_match(
                conn,
                tenant_id,
                result,
                purchase_order_id=result.order_id,
                synced_bill_id=_uuid(bill_row["id"]),
                delivery_receipt_id=_receipt_id(selected_order),
                evidence=_evidence_payload(bill, selected_order, result),
            )
            summary = summary.add(result)
        return summary

    def _load_orders(
        self, conn: psycopg.Connection[Any], tenant_id: UUID, bill: RawBillProjection
    ) -> tuple[OrderProjection, ...]:
        if bill.supplier_id is None:
            return ()
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, order_number, supplier_id, order_date, total_currency, source_reference
                FROM purchase_order
                WHERE tenant_id = %(tenant_id)s AND supplier_id = %(supplier_id)s
                  AND status NOT IN ('cancelled', 'draft')
                ORDER BY order_date, id
                """,
                {"tenant_id": tenant_id, "supplier_id": bill.supplier_id},
            )
            orders = list(cur.fetchall())
            result: list[OrderProjection] = []
            for order in orders:
                cur.execute(
                    """
                    SELECT id, line_number, workspace_product_id, description, ordered_quantity,
                           unit_price_amount, unit_price_currency
                    FROM purchase_order_line
                    WHERE tenant_id = %(tenant_id)s AND purchase_order_id = %(purchase_order_id)s
                    ORDER BY line_number
                    """,
                    {"tenant_id": tenant_id, "purchase_order_id": order["id"]},
                )
                line_rows = list(cur.fetchall())
                if not line_rows:
                    continue
                cur.execute(
                    """
                    SELECT id FROM supplier_confirmation
                    WHERE tenant_id = %(tenant_id)s AND purchase_order_id = %(purchase_order_id)s
                    ORDER BY confirmed_at DESC, id DESC LIMIT 1
                    """,
                    {"tenant_id": tenant_id, "purchase_order_id": order["id"]},
                )
                confirmation = cur.fetchone()
                confirmation_lines = []
                if confirmation:
                    cur.execute(
                        """
                        SELECT purchase_order_line_id, confirmed_quantity,
                               confirmed_unit_price_amount, confirmed_unit_price_currency
                        FROM supplier_confirmation_line
                        WHERE tenant_id = %(tenant_id)s AND supplier_confirmation_id = %(id)s
                        """,
                        {"tenant_id": tenant_id, "id": confirmation["id"]},
                    )
                    confirmation_lines = list(cur.fetchall())
                cur.execute(
                    """
                    SELECT r.id, rl.purchase_order_line_id, rl.received_quantity
                    FROM delivery_receipt r
                    JOIN delivery_receipt_line rl
                      ON rl.tenant_id = r.tenant_id AND rl.delivery_receipt_id = r.id
                    WHERE r.tenant_id = %(tenant_id)s
                      AND r.purchase_order_id = %(purchase_order_id)s
                      AND rl.tenant_id = %(tenant_id)s
                      AND rl.purchase_order_id = %(purchase_order_id)s
                    ORDER BY r.receipt_date, r.id
                    """,
                    {"tenant_id": tenant_id, "purchase_order_id": order["id"]},
                )
                receipt_rows = list(cur.fetchall())
                receipt_totals: dict[UUID, Decimal] = defaultdict(Decimal)
                receipt_ids: set[UUID] = set()
                for row in receipt_rows:
                    receipt_totals[_uuid(row["purchase_order_line_id"])] += Decimal(
                        str(row["received_quantity"])
                    )
                    receipt_ids.add(_uuid(row["id"]))
                result.append(
                    OrderProjection(
                        id=order["id"],
                        supplier_id=order["supplier_id"],
                        currency=order["total_currency"],
                        order_date=_as_date(order["order_date"]),
                        order_number=order["order_number"],
                        provider_order_reference=None,
                        document_references=(order["order_number"], order["source_reference"]),
                        lines=tuple(
                            OrderLineProjection(
                                row["id"],
                                row["line_number"],
                                row["ordered_quantity"],
                                _money(row["unit_price_amount"], row["unit_price_currency"]),
                                product_id=row["workspace_product_id"],
                                description=row["description"],
                            )
                            for row in line_rows
                        ),
                        confirmation=_evidence(
                            confirmation_lines,
                            quantity_key="confirmed_quantity",
                            price_amount_key="confirmed_unit_price_amount",
                            price_currency_key="confirmed_unit_price_currency",
                            source_ids=(_uuid(confirmation["id"]),),
                        )
                        if confirmation_lines
                        else EvidenceProjection("pending"),
                        receipt=_receipt_projection(receipt_rows, receipt_totals, receipt_ids),
                    )
                )
            return tuple(result)


def _receipt_projection(
    rows: list[Any], totals: dict[UUID, Decimal], ids: set[UUID]
) -> EvidenceProjection:
    if not rows:
        return EvidenceProjection("pending")
    unique_lines = tuple(
        EvidenceLineProjection(line_id, quantity)
        for line_id, quantity in sorted(totals.items(), key=lambda item: str(item[0]))
    )
    return EvidenceProjection("available", tuple(sorted(ids, key=str)), unique_lines)


def _receipt_id(order: OrderProjection | None) -> UUID | None:
    if order is None or order.receipt.state != "available" or not order.receipt.source_ids:
        return None
    return _uuid(order.receipt.source_ids[-1])


def run_three_way_sync(
    conn: psycopg.Connection[Any], tenant_id: UUID, connection_id: UUID
) -> ThreeWaySyncSummary:
    return ThreeWaySyncService().run(conn, tenant_id=tenant_id, connection_id=connection_id)


__all__ = [
    "THREE_WAY_RULESET",
    "THREE_WAY_RULESET_VERSION",
    "ThreeWaySyncService",
    "ThreeWaySyncSummary",
    "run_three_way_sync",
]
