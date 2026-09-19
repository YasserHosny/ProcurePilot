"""Persistence for an already-evaluated three-way match.

This module is deliberately a database adapter only.  The caller supplies a tenant-scoped
worker connection and has already resolved any internal accounting identifiers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .three_way_match_service import MatchDiscrepancy, ThreeWayMatchResult


@dataclass(frozen=True, slots=True)
class PersistedThreeWayMatch:
    match_id: UUID
    discrepancy_count: int
    inserted_discrepancy_count: int
    reopened_discrepancy_count: int
    auto_resolved_discrepancy_count: int


def _json_evidence(
    comparison: Mapping[str, object] | None, discrepancy: MatchDiscrepancy
) -> dict[str, object]:
    payload = dict(comparison or {})
    payload["order_line_id"] = str(discrepancy.order_line_id) if discrepancy.order_line_id else None
    payload["discrepancy_evidence"] = dict(discrepancy.evidence)
    return payload


def _evidence_value(evidence: Mapping[str, object] | None, key: str) -> object | None:
    """Return absent evidence as NULL, including when the caller supplies no snapshot."""
    return None if evidence is None else evidence.get(key)


def persist_three_way_match(
    conn: psycopg.Connection[Any],
    tenant_id: UUID,
    result: ThreeWayMatchResult,
    *,
    purchase_order_id: UUID | None = None,
    delivery_receipt_id: UUID | None = None,
    synced_bill_id: UUID | None = None,
    evidence: Mapping[str, object] | None = None,
) -> PersistedThreeWayMatch:
    """Persist one deterministic result using the caller-owned transaction.

    The connection must already be authenticated and scoped to ``tenant_id`` as a worker
    connection.  This function neither commits nor rolls back and performs no provider I/O.
    """
    if synced_bill_id is None and purchase_order_id is None and delivery_receipt_id is None:
        raise ValueError("at least one internal source relationship is required")

    match_id = _upsert_match(
        conn,
        tenant_id,
        result,
        purchase_order_id=purchase_order_id,
        delivery_receipt_id=delivery_receipt_id,
        synced_bill_id=synced_bill_id,
        evidence=evidence,
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, discrepancy_type, purchase_order_id, evidence, source_hash, status
            FROM reconciliation_discrepancy
            WHERE tenant_id = %s AND three_way_match_id = %s
            FOR UPDATE
            """,
            (tenant_id, match_id),
        )
        existing = list(cur.fetchall())

    existing_by_key = {
        _discrepancy_key(row["discrepancy_type"], row["purchase_order_id"], row["evidence"]): row
        for row in existing
    }
    active_keys = {
        _discrepancy_key(item.type, purchase_order_id, _json_evidence(evidence, item))
        for item in result.discrepancies
    }
    inserted = reopened = auto_resolved = 0

    for item in result.discrepancies:
        key = _discrepancy_key(item.type, purchase_order_id, _json_evidence(evidence, item))
        current = existing_by_key.get(key)
        item_evidence = _json_evidence(evidence, item)
        if current is None:
            _insert_discrepancy(
                conn,
                tenant_id,
                match_id,
                result,
                item,
                purchase_order_id,
                synced_bill_id,
                item_evidence,
            )
            inserted += 1
        else:
            was_resolved = current["status"] == "resolved"
            changed_source = current["source_hash"] != result.source_hash
            _update_discrepancy(
                conn,
                tenant_id,
                current["id"],
                match_id,
                result,
                item,
                purchase_order_id,
                synced_bill_id,
                item_evidence,
                reopen=was_resolved and changed_source,
            )
            reopened += int(was_resolved and changed_source)

    for row in existing:
        key = _discrepancy_key(row["discrepancy_type"], row["purchase_order_id"], row["evidence"])
        if key not in active_keys and row["status"] == "open":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE reconciliation_discrepancy
                    SET status = 'resolved', resolved_by = NULL, resolved_at = now(),
                        resolution_note = NULL
                    WHERE tenant_id = %s AND id = %s AND status = 'open'
                    """,
                    (tenant_id, row["id"]),
                )
            auto_resolved += 1

    return PersistedThreeWayMatch(
        match_id=match_id,
        discrepancy_count=len(result.discrepancies),
        inserted_discrepancy_count=inserted,
        reopened_discrepancy_count=reopened,
        auto_resolved_discrepancy_count=auto_resolved,
    )


def _discrepancy_key(
    discrepancy_type: str, purchase_order_id: UUID | str | None, evidence: object
) -> tuple[str, str | None, str | None]:
    evidence_mapping = evidence if isinstance(evidence, Mapping) else {}
    order_line_id = evidence_mapping.get("order_line_id")
    return (
        discrepancy_type,
        str(purchase_order_id) if purchase_order_id else None,
        (str(order_line_id) if order_line_id else None),
    )


def _upsert_match(
    conn: psycopg.Connection[Any],
    tenant_id: UUID,
    result: ThreeWayMatchResult,
    *,
    purchase_order_id: UUID | None,
    delivery_receipt_id: UUID | None,
    synced_bill_id: UUID | None,
    evidence: Mapping[str, object] | None,
) -> UUID:
    values = (
        tenant_id,
        purchase_order_id,
        delivery_receipt_id,
        synced_bill_id,
        result.result,
        result.ruleset_version,
        _evidence_value(evidence, "ordered_quantity"),
        _evidence_value(evidence, "confirmed_quantity"),
        _evidence_value(evidence, "received_quantity"),
        _evidence_value(evidence, "invoiced_quantity"),
        _evidence_value(evidence, "ordered_unit_price_amount"),
        _evidence_value(evidence, "ordered_unit_price_currency"),
        _evidence_value(evidence, "invoiced_unit_price_amount"),
        _evidence_value(evidence, "invoiced_unit_price_currency"),
        _evidence_value(evidence, "ordered_total_amount"),
        _evidence_value(evidence, "ordered_total_currency"),
        _evidence_value(evidence, "invoiced_total_amount"),
        _evidence_value(evidence, "invoiced_total_currency"),
        result.source_hash,
    )
    columns = """
        tenant_id, purchase_order_id, delivery_receipt_id, synced_bill_id, result,
        tolerance_ruleset_version, ordered_quantity, confirmed_quantity, received_quantity,
        invoiced_quantity, ordered_unit_price_amount, ordered_unit_price_currency,
        invoiced_unit_price_amount, invoiced_unit_price_currency, ordered_total_amount,
        ordered_total_currency, invoiced_total_amount, invoiced_total_currency, source_hash
    """
    update = """
        result = EXCLUDED.result, tolerance_ruleset_version = EXCLUDED.tolerance_ruleset_version,
        purchase_order_id = EXCLUDED.purchase_order_id,
        delivery_receipt_id = EXCLUDED.delivery_receipt_id,
        ordered_quantity = EXCLUDED.ordered_quantity,
        confirmed_quantity = EXCLUDED.confirmed_quantity,
        received_quantity = EXCLUDED.received_quantity,
        invoiced_quantity = EXCLUDED.invoiced_quantity,
        ordered_unit_price_amount = EXCLUDED.ordered_unit_price_amount,
        ordered_unit_price_currency = EXCLUDED.ordered_unit_price_currency,
        invoiced_unit_price_amount = EXCLUDED.invoiced_unit_price_amount,
        invoiced_unit_price_currency = EXCLUDED.invoiced_unit_price_currency,
        ordered_total_amount = EXCLUDED.ordered_total_amount,
        ordered_total_currency = EXCLUDED.ordered_total_currency,
        invoiced_total_amount = EXCLUDED.invoiced_total_amount,
        invoiced_total_currency = EXCLUDED.invoiced_total_currency,
        source_hash = EXCLUDED.source_hash, evaluated_at = now(), updated_at = now()
    """
    if synced_bill_id is not None:
        query = f"""
            INSERT INTO three_way_match ({columns}) VALUES ({", ".join(["%s"] * len(values))})
            ON CONFLICT (tenant_id, synced_bill_id) WHERE synced_bill_id IS NOT NULL
            DO UPDATE SET {update}
            RETURNING id
        """
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()
        return row[0]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM three_way_match
            WHERE tenant_id = %s AND synced_bill_id IS NULL
              AND purchase_order_id IS NOT DISTINCT FROM %s
              AND delivery_receipt_id IS NOT DISTINCT FROM %s
            ORDER BY updated_at DESC LIMIT 1 FOR UPDATE
            """,
            (tenant_id, purchase_order_id, delivery_receipt_id),
        )
        row = cur.fetchone()
        if row is not None:
            update_params = (
                result.result,
                result.ruleset_version,
                purchase_order_id,
                delivery_receipt_id,
                values[6],
                values[7],
                values[8],
                values[9],
                values[10],
                values[11],
                values[12],
                values[13],
                values[14],
                values[15],
                values[16],
                values[17],
                result.source_hash,
                tenant_id,
                row[0],
            )
            cur.execute(
                """
                UPDATE three_way_match
                SET result = %s, tolerance_ruleset_version = %s,
                    purchase_order_id = %s, delivery_receipt_id = %s,
                    ordered_quantity = %s, confirmed_quantity = %s, received_quantity = %s,
                    invoiced_quantity = %s, ordered_unit_price_amount = %s,
                    ordered_unit_price_currency = %s, invoiced_unit_price_amount = %s,
                    invoiced_unit_price_currency = %s, ordered_total_amount = %s,
                    ordered_total_currency = %s, invoiced_total_amount = %s,
                    invoiced_total_currency = %s, source_hash = %s,
                    evaluated_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s
                RETURNING id
                """,
                update_params,
            )
            return cur.fetchone()[0]
        placeholders = ", ".join(["%s"] * len(values))
        cur.execute(
            f"INSERT INTO three_way_match ({columns}) VALUES ({placeholders}) RETURNING id", values
        )
        return cur.fetchone()[0]


def _insert_discrepancy(
    conn: psycopg.Connection[Any],
    tenant_id: UUID,
    match_id: UUID,
    result: ThreeWayMatchResult,
    item: MatchDiscrepancy,
    purchase_order_id: UUID | None,
    synced_bill_id: UUID | None,
    evidence: dict[str, object],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO reconciliation_discrepancy
              (tenant_id, discrepancy_type, synced_bill_id, status, detected_at,
               three_way_match_id, purchase_order_id, evidence, source_hash, source_updated_at)
            VALUES (%s, %s, %s, 'open', now(), %s, %s, %s, %s, now())
            """,
            (
                tenant_id,
                item.type,
                synced_bill_id,
                match_id,
                purchase_order_id,
                Jsonb(evidence),
                result.source_hash,
            ),
        )


def _update_discrepancy(
    conn: psycopg.Connection[Any],
    tenant_id: UUID,
    discrepancy_id: UUID,
    match_id: UUID,
    result: ThreeWayMatchResult,
    item: MatchDiscrepancy,
    purchase_order_id: UUID | None,
    synced_bill_id: UUID | None,
    evidence: dict[str, object],
    *,
    reopen: bool,
) -> None:
    resolution = """
        status = CASE WHEN %s THEN 'open' ELSE status END,
        resolved_by = CASE WHEN %s THEN NULL ELSE resolved_by END,
        resolved_at = CASE WHEN %s THEN NULL ELSE resolved_at END,
        resolution_note = CASE WHEN %s THEN NULL ELSE resolution_note END,
        reopened_at = CASE WHEN %s THEN now() ELSE reopened_at END
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE reconciliation_discrepancy
            SET discrepancy_type = %s, synced_bill_id = %s, three_way_match_id = %s,
                purchase_order_id = %s, evidence = %s, source_hash = %s,
                source_updated_at = now(), {resolution}
            WHERE tenant_id = %s AND id = %s
            """,
            (
                item.type,
                synced_bill_id,
                match_id,
                purchase_order_id,
                Jsonb(evidence),
                result.source_hash,
                reopen,
                reopen,
                reopen,
                reopen,
                reopen,
                tenant_id,
                discrepancy_id,
            ),
        )


__all__ = ["PersistedThreeWayMatch", "persist_three_way_match"]
