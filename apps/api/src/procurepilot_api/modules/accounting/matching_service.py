"""SC-002 note: bills auto-match purchase records ≥90% (vs constitution product match ≥92%)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


# Date column reasoning:
# We select `ordered_at` as the purchase record's date for 14-day matching (FR-007).
# In `20260821000031_purchase_saving_records.sql`, `purchase_record` defines three timestamps:
# `ordered_at`, `delivered_at`, and `recorded_at`. `ordered_at` represents the commercial
# transaction date when the purchase order was placed with the supplier. In contrast,
# `delivered_at` represents when goods arrived; as shown by the CHECK constraint
# `(delivered_at is null or ordered_at is null or delivered_at >= ordered_at)` and the
# `purchase_delivery_result` enum containing 'ordered', `delivered_at` is legitimately NULL
# for pending/ordered purchases. Using `delivered_at` would therefore completely exclude any
# undelivered or pending orders from matching incoming supplier bills. When querying the database,
# we fall back to `recorded_at` if `ordered_at` was not populated via
# `coalesce(ordered_at, recorded_at)::date`.


@dataclass(frozen=True)
class BillForMatching:
    """A synced bill projection containing the fields necessary for automatic matching."""

    amount: Decimal
    currency: str
    bill_date: date

    def __init__(
        self,
        amount: Decimal | str | float,
        currency: str,
        bill_date: date | datetime,
    ) -> None:
        if isinstance(bill_date, datetime):
            bill_date = bill_date.date()
        object.__setattr__(self, "amount", Decimal(str(amount)))
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "bill_date", bill_date)


@dataclass(frozen=True)
class PurchaseRecordCandidate:
    """A purchase record projection evaluated as a candidate for automatic matching."""

    id: UUID
    total_paid_amount: Decimal
    total_paid_currency: str
    ordered_at: date

    def __init__(
        self,
        id: UUID,
        total_paid_amount: Decimal | str | float,
        total_paid_currency: str,
        ordered_at: date | datetime | None = None,
        *,
        purchase_date: date | datetime | None = None,
    ) -> None:
        target_date = ordered_at if ordered_at is not None else purchase_date
        if target_date is None:
            raise ValueError("Either ordered_at or purchase_date must be provided")
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "total_paid_amount", Decimal(str(total_paid_amount)))
        object.__setattr__(self, "total_paid_currency", total_paid_currency)
        object.__setattr__(self, "ordered_at", target_date)

    @property
    def purchase_date(self) -> date:
        """Alias for ordered_at."""
        return self.ordered_at


def select_match(
    bill: BillForMatching,
    candidates: list[PurchaseRecordCandidate],
) -> UUID | None:
    """Pure function selecting a single qualifying purchase record candidate (FR-007).

    Rules:
    - Same currency: candidate.total_paid_currency == bill.currency
    - Amount within rounding tolerance: abs(candidate.total_paid_amount - bill.amount) <= 0.01
    - Date within window: abs((candidate.ordered_at - bill.bill_date).days) <= 14

    Returns:
    - candidate.id if EXACTLY ONE candidate qualifies.
    - None if zero or >1 candidates qualify (ties are left unmatched for manual review).
    """
    qualifying: list[PurchaseRecordCandidate] = []
    for cand in candidates:
        if cand.total_paid_currency != bill.currency:
            continue
        if abs(cand.total_paid_amount - bill.amount) > Decimal("0.01"):
            continue
        date_diff = abs((cand.ordered_at - bill.bill_date).days)
        if date_diff > 14:
            continue
        qualifying.append(cand)

    if len(qualifying) == 1:
        return qualifying[0].id
    return None


class MatchingService:
    """Service layer for matching synced bills to purchase records (T019, FR-007)."""

    def match_bill(
        self,
        conn: psycopg.Connection,
        *,
        tenant_id: UUID,
        bill_row: dict[str, Any],
    ) -> UUID | None:
        """Query candidate purchase records for bill_row, select match, and persist match.

        Operates within the caller's tenant-scoped database session.
        Returns the matched purchase_record_id if matched, otherwise None.
        """
        supplier_id = bill_row.get("matched_supplier_id")
        if not supplier_id:
            return None

        raw_bill_date = bill_row["bill_date"]
        if isinstance(raw_bill_date, str):
            bill_date = date.fromisoformat(raw_bill_date)
        elif isinstance(raw_bill_date, datetime):
            bill_date = raw_bill_date.date()
        else:
            bill_date = raw_bill_date

        bill = BillForMatching(
            amount=Decimal(str(bill_row["amount"])),
            currency=str(bill_row["currency"]),
            bill_date=bill_date,
        )

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select pr.id,
                       pr.total_paid_amount,
                       pr.total_paid_currency,
                       coalesce(pr.ordered_at, pr.recorded_at) as purchase_date
                from purchase_record pr
                where pr.tenant_id = %(tenant_id)s
                  and pr.supplier_id = %(supplier_id)s
                  and not exists (
                      select 1 from purchase_bill_match m
                      where m.tenant_id = %(tenant_id)s
                        and m.purchase_record_id = pr.id
                  )
                """,
                {"tenant_id": tenant_id, "supplier_id": supplier_id},
            )
            rows = cur.fetchall()

        candidates: list[PurchaseRecordCandidate] = []
        for r in rows:
            raw_pdate = r["purchase_date"]
            if isinstance(raw_pdate, datetime):
                pdate = raw_pdate.date()
            elif isinstance(raw_pdate, str):
                pdate = date.fromisoformat(raw_pdate[:10])
            else:
                pdate = raw_pdate

            candidates.append(
                PurchaseRecordCandidate(
                    id=UUID(str(r["id"])),
                    total_paid_amount=Decimal(str(r["total_paid_amount"])),
                    total_paid_currency=str(r["total_paid_currency"]),
                    ordered_at=pdate,
                )
            )

        matched_id = select_match(bill, candidates)
        if matched_id is None:
            return None

        synced_bill_id = UUID(str(bill_row["id"]))
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into purchase_bill_match (
                    tenant_id,
                    synced_bill_id,
                    purchase_record_id,
                    match_method,
                    matched_by,
                    matched_at
                ) values (
                    %(tenant_id)s,
                    %(synced_bill_id)s,
                    %(purchase_record_id)s,
                    'automatic',
                    null,
                    now()
                )
                """,
                {
                    "tenant_id": tenant_id,
                    "synced_bill_id": synced_bill_id,
                    "purchase_record_id": matched_id,
                },
            )

        return matched_id
