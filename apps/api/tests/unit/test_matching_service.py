"""Unit tests for MatchingService.select_match (task T020, US2, FR-007).

Tests the pure selection function without a database or network fixtures.
Covers:
- Exact amount and date match
- Rounding tolerance (boundary at ±$0.01 and outside ±$0.01)
- 14-day date window boundaries in both directions (bill before purchase, bill after purchase)
- Multiple equally-qualifying candidates left unmatched (tie-breaking to None per FR-007)
- Zero candidates (empty list or no matches)
- Candidate currency mismatch exclusion despite numerical amount match
- Single qualifying candidate amidst disqualified candidates
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from procurepilot_api.modules.accounting.matching_service import (
    BillForMatching,
    PurchaseRecordCandidate,
    select_match,
)


def test_exact_amount_and_date_match() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("1250.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("1250.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),
        )
    ]

    assert select_match(bill, candidates) == candidate_id


def test_match_just_within_rounding_tolerance_positive() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("100.01"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),
        )
    ]

    assert select_match(bill, candidates) == candidate_id


def test_match_just_within_rounding_tolerance_negative() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("99.99"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),
        )
    ]

    assert select_match(bill, candidates) == candidate_id


def test_no_match_just_outside_rounding_tolerance_higher() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("100.02"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),
        )
    ]

    assert select_match(bill, candidates) is None


def test_no_match_just_outside_rounding_tolerance_lower() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("99.98"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),
        )
    ]

    assert select_match(bill, candidates) is None


def test_date_window_purchase_14_days_before_bill_just_inside() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("200.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("200.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 1),  # Exactly 14 days before
        )
    ]

    assert select_match(bill, candidates) == candidate_id


def test_date_window_purchase_15_days_before_bill_just_outside() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("200.00"),
        currency="USD",
        bill_date=date(2026, 5, 15),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("200.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 4, 30),  # 15 days before
        )
    ]

    assert select_match(bill, candidates) is None


def test_date_window_purchase_14_days_after_bill_just_inside() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("200.00"),
        currency="USD",
        bill_date=date(2026, 5, 1),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("200.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 15),  # Exactly 14 days after
        )
    ]

    assert select_match(bill, candidates) == candidate_id


def test_date_window_purchase_15_days_after_bill_just_outside() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("200.00"),
        currency="USD",
        bill_date=date(2026, 5, 1),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("200.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 16),  # 15 days after
        )
    ]

    assert select_match(bill, candidates) is None


def test_multiple_equally_qualifying_candidates_returns_none() -> None:
    bill = BillForMatching(
        amount=Decimal("500.00"),
        currency="USD",
        bill_date=date(2026, 5, 10),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("500.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 10),
        ),
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("500.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 10),
        ),
    ]

    # FR-007: ties are never auto-picked, must return None for manual review
    assert select_match(bill, candidates) is None


def test_multiple_qualifying_candidates_different_amounts_within_tolerance_returns_none() -> None:
    bill = BillForMatching(
        amount=Decimal("500.00"),
        currency="USD",
        bill_date=date(2026, 5, 10),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("500.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 10),
        ),
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("500.01"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 12),
        ),
    ]

    assert select_match(bill, candidates) is None


def test_zero_candidates_empty_list_returns_none() -> None:
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 10),
    )
    assert select_match(bill, []) is None


def test_zero_qualifying_candidates_returns_none() -> None:
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 10),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("999.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 5, 10),
        ),
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("100.00"),
            total_paid_currency="USD",
            ordered_at=date(2026, 1, 1),
        ),
    ]
    assert select_match(bill, candidates) is None


def test_different_currency_excluded_even_if_amount_matches_numerically() -> None:
    candidate_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("100.00"),
        currency="USD",
        bill_date=date(2026, 5, 10),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=candidate_id,
            total_paid_amount=Decimal("100.00"),
            total_paid_currency="EUR",  # Different currency
            ordered_at=date(2026, 5, 10),
        )
    ]

    assert select_match(bill, candidates) is None


def test_single_qualifying_amongst_multiple_non_qualifying() -> None:
    valid_id = uuid4()
    bill = BillForMatching(
        amount=Decimal("350.00"),
        currency="GBP",
        bill_date=date(2026, 6, 10),
    )
    candidates = [
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("350.00"),
            total_paid_currency="USD",  # Wrong currency
            ordered_at=date(2026, 6, 10),
        ),
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("500.00"),  # Wrong amount
            total_paid_currency="GBP",
            ordered_at=date(2026, 6, 10),
        ),
        PurchaseRecordCandidate(
            id=uuid4(),
            total_paid_amount=Decimal("350.00"),
            total_paid_currency="GBP",
            ordered_at=date(2026, 4, 1),  # Too old (>14 days)
        ),
        PurchaseRecordCandidate(
            id=valid_id,
            total_paid_amount=Decimal("350.01"),  # Valid (within 0.01 and within 14 days)
            total_paid_currency="GBP",
            ordered_at=date(2026, 6, 8),
        ),
    ]

    assert select_match(bill, candidates) == valid_id
