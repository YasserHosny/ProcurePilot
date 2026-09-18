"""Service layer for reconciliation discrepancies (R3.1, US3, task T028).

Implements ReconciliationService:
- recompute_discrepancies: derives current exception set (unmatched bills, unmatched
  purchases > 30 days, amount mismatches) and updates reconciliation_discrepancy table.
  Runs on caller's tenant-scoped worker connection during sync.
- resolve: allows owner or buyer to mark a discrepancy as resolved with an optional note,
  enforcing 409 ConflictError if already resolved, and recording an audit event.
- list_discrepancies: returns cursor-paginated list of discrepancies with denormalized
  detail objects (supplier/vendor, amount, currency, date).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import Depends
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.accounting.schemas import (
    ReconciliationDiscrepancy,
    ReconciliationDiscrepancyList,
)
from procurepilot_api.modules.accounting.service import (
    _decode_cursor,
    _encode_cursor,
    _record_audit,
)
from procurepilot_api.modules.offers.service import _authenticated_db

logger = logging.getLogger(__name__)


def _format_discrepancy_row(r: dict[str, Any]) -> dict[str, Any]:
    """Populate nested read-only detail objects from joined query columns (decision #1)."""
    synced_bill_detail = None
    if r.get("synced_bill_id") is not None:
        synced_bill_detail = {
            "vendor_name": r.get("bill_vendor_name") or "",
            "amount": str(r.get("bill_amount")),
            "currency": str(r.get("bill_currency")),
            "bill_date": r.get("bill_bill_date"),
        }

    purchase_record_detail = None
    if r.get("purchase_record_id") is not None:
        purchase_record_detail = {
            "supplier_name": r.get("pr_supplier_name"),
            "amount": str(r.get("pr_amount")),
            "currency": str(r.get("pr_currency")),
            "date": r.get("pr_date"),
        }

    return {
        "id": r["id"],
        "discrepancy_type": r["discrepancy_type"],
        "synced_bill_id": r.get("synced_bill_id"),
        "purchase_record_id": r.get("purchase_record_id"),
        "status": r["status"],
        "detected_at": r["detected_at"],
        "resolved_by": r.get("resolved_by"),
        "resolved_at": r.get("resolved_at"),
        "resolution_note": r.get("resolution_note"),
        "synced_bill_detail": synced_bill_detail,
        "purchase_record_detail": purchase_record_detail,
    }


class ReconciliationService:
    """T028: Derives, recomputes, resolves, and lists reconciliation discrepancies."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def recompute_discrepancies(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> dict[str, int]:
        """Recompute discrepancies for the given connection on the provided connection.

        Runs on the SAME tenant-scoped worker connection as SyncService's pipeline.
        Derives all three shapes:
        - unmatched_bill: every synced_bill for this connection with no purchase_bill_match row.
        - unmatched_purchase: every purchase_record for this tenant with no purchase_bill_match,
          whose supplier has a synced_vendor on this connection (decision #2), and whose date
          (coalesce(ordered_at, recorded_at)) is > 30 days old (FR-010).
        - amount_mismatch: every purchase_bill_match on this connection where bill amount
          and purchase_record total_paid_amount differ by > $0.01 OR differ in currency.

        Lifecycle:
        - If new condition: INSERT with status='open', detected_at=now().
        - If existing condition is 'resolved': REOPEN if underlying records
          updated_at > resolved_at; leave resolved if unchanged.
        - If existing condition is 'open': leave untouched (preserving detected_at).
        - If existing OPEN condition no longer holds: auto-resolve with status='resolved',
          resolved_at=now(), resolved_by=null (decision #3).
        """
        current_conditions: dict[tuple[str, UUID | None, UUID | None], Any] = {}

        with conn.cursor(row_factory=dict_row) as cur:
            # 1. unmatched_bill
            cur.execute(
                """
                select b.id as synced_bill_id, b.updated_at
                from synced_bill b
                where b.tenant_id = %(tenant_id)s
                  and b.connection_id = %(connection_id)s
                  and not exists (
                      select 1
                      from purchase_bill_match m
                      where m.tenant_id = b.tenant_id
                        and m.synced_bill_id = b.id
                  )
                """,
                {"tenant_id": tenant_id, "connection_id": connection_id},
            )
            for row in cur.fetchall():
                key = ("unmatched_bill", UUID(str(row["synced_bill_id"])), None)
                current_conditions[key] = row["updated_at"]

            # 2. unmatched_purchase (decision #2: scoped to suppliers linked via synced_vendor)
            cur.execute(
                """
                select pr.id as purchase_record_id, pr.updated_at
                from purchase_record pr
                where pr.tenant_id = %(tenant_id)s
                  and not exists (
                      select 1
                      from purchase_bill_match m
                      where m.tenant_id = pr.tenant_id
                        and m.purchase_record_id = pr.id
                  )
                  and exists (
                      select 1
                      from synced_vendor sv
                      where sv.tenant_id = pr.tenant_id
                        and sv.connection_id = %(connection_id)s
                        and sv.matched_supplier_id = pr.supplier_id
                  )
                  and coalesce(pr.ordered_at, pr.recorded_at) < now() - interval '30 days'
                """,
                {"tenant_id": tenant_id, "connection_id": connection_id},
            )
            for row in cur.fetchall():
                key = ("unmatched_purchase", None, UUID(str(row["purchase_record_id"])))
                current_conditions[key] = row["updated_at"]

            # 3. amount_mismatch
            cur.execute(
                """
                select
                    m.synced_bill_id,
                    m.purchase_record_id,
                    greatest(b.updated_at, pr.updated_at) as updated_at
                from purchase_bill_match m
                join synced_bill b
                    on b.tenant_id = m.tenant_id and b.id = m.synced_bill_id
                join purchase_record pr
                    on pr.tenant_id = m.tenant_id and pr.id = m.purchase_record_id
                where m.tenant_id = %(tenant_id)s
                  and b.connection_id = %(connection_id)s
                  and (
                      b.currency <> pr.total_paid_currency
                      or abs(b.amount - pr.total_paid_amount) > 0.01
                  )
                """,
                {"tenant_id": tenant_id, "connection_id": connection_id},
            )
            for row in cur.fetchall():
                key = (
                    "amount_mismatch",
                    UUID(str(row["synced_bill_id"])),
                    UUID(str(row["purchase_record_id"])),
                )
                current_conditions[key] = row["updated_at"]

            # 4. Fetch existing discrepancies in scope for this tenant/connection
            cur.execute(
                """
                select d.id, d.discrepancy_type, d.synced_bill_id, d.purchase_record_id,
                       d.status, d.detected_at, d.resolved_at, d.resolved_by, d.resolution_note
                from reconciliation_discrepancy d
                where d.tenant_id = %(tenant_id)s
                  and (
                      (d.synced_bill_id is not null and exists (
                          select 1 from synced_bill b
                          where b.tenant_id = d.tenant_id
                            and b.id = d.synced_bill_id
                            and b.connection_id = %(connection_id)s
                      ))
                      or
                      (d.synced_bill_id is null and d.discrepancy_type = 'unmatched_purchase')
                  )
                """,
                {"tenant_id": tenant_id, "connection_id": connection_id},
            )
            existing_rows = cur.fetchall()

            existing_map: dict[tuple[str, UUID | None, UUID | None], dict[str, Any]] = {}
            for r in existing_rows:
                b_id = UUID(str(r["synced_bill_id"])) if r["synced_bill_id"] else None
                p_id = UUID(str(r["purchase_record_id"])) if r["purchase_record_id"] else None
                key = (str(r["discrepancy_type"]), b_id, p_id)
                existing_map[key] = dict(r)

            inserted_count = 0
            reopened_count = 0
            auto_resolved_count = 0

            # Insert new or reopen stale-resolved
            for key, underlying_updated_at in current_conditions.items():
                disc_type, bill_id, pr_id = key
                if key not in existing_map:
                    cur.execute(
                        """
                        insert into reconciliation_discrepancy (
                            tenant_id, discrepancy_type, synced_bill_id, purchase_record_id,
                            status, detected_at
                        ) values (
                            %(tenant_id)s, %(discrepancy_type)s,
                            %(synced_bill_id)s, %(purchase_record_id)s,
                            'open', now()
                        )
                        """,
                        {
                            "tenant_id": tenant_id,
                            "discrepancy_type": disc_type,
                            "synced_bill_id": bill_id,
                            "purchase_record_id": pr_id,
                        },
                    )
                    inserted_count += 1
                else:
                    existing = existing_map[key]
                    if existing["status"] == "resolved":
                        resolved_at = existing.get("resolved_at")
                        if (
                            underlying_updated_at is not None
                            and resolved_at is not None
                            and underlying_updated_at > resolved_at
                        ):
                            cur.execute(
                                """
                                update reconciliation_discrepancy
                                set status = 'open',
                                    resolved_by = null,
                                    resolved_at = null,
                                    resolution_note = null
                                where id = %(id)s and tenant_id = %(tenant_id)s
                                """,
                                {"id": existing["id"], "tenant_id": tenant_id},
                            )
                            reopened_count += 1

            # Auto-resolve previously open discrepancies whose condition
            # no longer holds (decision #3)
            for key, existing in existing_map.items():
                if existing["status"] == "open" and key not in current_conditions:
                    cur.execute(
                        """
                        update reconciliation_discrepancy
                        set status = 'resolved',
                            resolved_at = now(),
                            resolved_by = null,
                            resolution_note = %(auto_note)s
                        where id = %(id)s and tenant_id = %(tenant_id)s
                        """,
                        {
                            "id": existing["id"],
                            "tenant_id": tenant_id,
                            "auto_note": (
                                "Automatically resolved — underlying condition no longer applies"
                            ),
                        },
                    )
                    auto_resolved_count += 1

        unmatched_bills_count = sum(
            1 for (t, _, _) in current_conditions if t == "unmatched_bill"
        )
        unmatched_purchases_count = sum(
            1 for (t, _, _) in current_conditions if t == "unmatched_purchase"
        )
        amount_mismatches_count = sum(
            1 for (t, _, _) in current_conditions if t == "amount_mismatch"
        )

        return {
            "unmatched_bills": unmatched_bills_count,
            "unmatched_purchases": unmatched_purchases_count,
            "amount_mismatches": amount_mismatches_count,
            "total_open": len(current_conditions),
            "inserted": inserted_count,
            "reopened": reopened_count,
            "auto_resolved": auto_resolved_count,
        }

    def resolve(
        self,
        member: CurrentMember,
        *,
        discrepancy_id: UUID,
        note: str | None = None,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        """Mark an open discrepancy resolved by an owner or buyer (FR-011, T028).

        Refuses with ConflictError (409) if already resolved.
        Refuses with NotFoundError (404) if unknown or cross-tenant.
        Records accounting.discrepancy_resolved audit event.
        """
        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, tenant_id, discrepancy_type, status,
                           synced_bill_id, purchase_record_id
                    from reconciliation_discrepancy
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {"id": discrepancy_id, "tenant_id": member.tenant_id},
                )
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError(
                        details={
                            "resource": "reconciliation_discrepancy",
                            "id": str(discrepancy_id),
                        }
                    )

                if row["status"] == "resolved":
                    raise ConflictError(
                        details={
                            "resource": "reconciliation_discrepancy",
                            "reason": "already_resolved",
                            "id": str(discrepancy_id),
                        }
                    )

                cur.execute(
                    """
                    update reconciliation_discrepancy
                    set status = 'resolved',
                        resolved_by = %(resolved_by)s,
                        resolved_at = now(),
                        resolution_note = %(note)s
                    where id = %(id)s and tenant_id = %(tenant_id)s
                    """,
                    {
                        "id": discrepancy_id,
                        "tenant_id": member.tenant_id,
                        "resolved_by": member.membership_id,
                        "note": note,
                    },
                )

                cur.execute(
                    """
                    select
                        d.id,
                        d.discrepancy_type,
                        d.synced_bill_id,
                        d.purchase_record_id,
                        d.status,
                        d.detected_at,
                        d.resolved_by,
                        d.resolved_at,
                        d.resolution_note,
                        b.id as bill_id,
                        sv.display_name as bill_vendor_name,
                        b.amount as bill_amount,
                        b.currency as bill_currency,
                        b.bill_date as bill_bill_date,
                        pr.id as pr_id,
                        s.name as pr_supplier_name,
                        pr.total_paid_amount as pr_amount,
                        pr.total_paid_currency as pr_currency,
                        coalesce(pr.ordered_at, pr.recorded_at)::date as pr_date
                    from reconciliation_discrepancy d
                    left join synced_bill b
                        on b.tenant_id = d.tenant_id and b.id = d.synced_bill_id
                    left join synced_vendor sv
                        on sv.tenant_id = b.tenant_id and sv.id = b.vendor_id
                    left join purchase_record pr
                        on pr.tenant_id = d.tenant_id and pr.id = d.purchase_record_id
                    left join supplier s
                        on s.tenant_id = pr.tenant_id and s.id = pr.supplier_id
                    where d.id = %(id)s and d.tenant_id = %(tenant_id)s
                    """,
                    {"id": discrepancy_id, "tenant_id": member.tenant_id},
                )
                updated_row = dict(cur.fetchone())
            conn.commit()

        _record_audit(
            bearer_token=bearer_token,
            member=member,
            action="accounting.discrepancy_resolved",
            target={
                "reconciliation_discrepancy_id": str(discrepancy_id),
                "discrepancy_type": str(row["discrepancy_type"]),
                "note": note,
            },
        )

        return _format_discrepancy_row(updated_row)

    def list_discrepancies(
        self,
        member: CurrentMember,
        *,
        cursor: str | None = None,
        limit: int = 50,
        status: str = "open",
    ) -> ReconciliationDiscrepancyList:
        """Return cursor-paginated list of discrepancies for the member's tenant (T028).

        Populates denormalized synced_bill_detail and purchase_record_detail (decision #1).
        """
        offset = _decode_cursor(cursor)
        fetch_limit = min(max(limit, 1), 100)

        query = """
            select
                d.id,
                d.discrepancy_type,
                d.synced_bill_id,
                d.purchase_record_id,
                d.status,
                d.detected_at,
                d.resolved_by,
                d.resolved_at,
                d.resolution_note,
                b.id as bill_id,
                sv.display_name as bill_vendor_name,
                b.amount as bill_amount,
                b.currency as bill_currency,
                b.bill_date as bill_bill_date,
                pr.id as pr_id,
                s.name as pr_supplier_name,
                pr.total_paid_amount as pr_amount,
                pr.total_paid_currency as pr_currency,
                coalesce(pr.ordered_at, pr.recorded_at)::date as pr_date
            from reconciliation_discrepancy d
            left join synced_bill b
                on b.tenant_id = d.tenant_id and b.id = d.synced_bill_id
            left join synced_vendor sv
                on sv.tenant_id = b.tenant_id and sv.id = b.vendor_id
            left join purchase_record pr
                on pr.tenant_id = d.tenant_id and pr.id = d.purchase_record_id
            left join supplier s
                on s.tenant_id = pr.tenant_id and s.id = pr.supplier_id
            where d.tenant_id = %(tenant_id)s
              and d.status = %(status)s
            order by d.detected_at desc, d.id desc
            offset %(offset)s limit %(limit)s
        """

        with _authenticated_db(self._settings, member) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    query,
                    {
                        "tenant_id": member.tenant_id,
                        "status": status,
                        "offset": offset,
                        "limit": fetch_limit + 1,
                    },
                )
                rows = [dict(r) for r in cur.fetchall()]

        has_more = len(rows) > fetch_limit
        page_rows = rows[:fetch_limit]
        next_cursor = _encode_cursor(offset + fetch_limit) if has_more else None

        items = [
            ReconciliationDiscrepancy.model_validate(_format_discrepancy_row(r))
            for r in page_rows
        ]
        return ReconciliationDiscrepancyList(items=items, next_cursor=next_cursor)


def get_reconciliation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReconciliationService:
    return ReconciliationService(settings)
