"""Pure schedule math for R2.5 — task T009 (FR-003, FR-006).

The window functions are the reporting pipeline's calendar: every scheduled artifact and
digest derives its period from them, so they are pure, timezone-explicit, and unit-tested
without a database. The imports are deferred into the test bodies — until the backend lane
lands `modules/reports/schedules.py` (T011) these are red for the right reason, and they
drive the implementation.

Contracts pinned here:

* derive_weekly_window(run_at, timezone_name) — the PRIOR COMPLETE period window ending the
  day before the run date, expressed as calendar dates in the workspace's reporting
  timezone. A run's own week is never reported: a window that is still in progress would
  silently change under later edits, and an artifact must be reproducible (FR-016).

* next_run_after(weekday, after, timezone_name) — the next instant STRICTLY AFTER `after`
  whose local date is the given weekday (0 = Monday, matching the stored smallint), at
  midnight local time, returned in UTC. "Strictly after" matters: creating a schedule on
  its own weekday after midnight must schedule the NEXT week, never a window that already
  started.

* period_idempotency_key(schedule_id, period_start) — the deterministic per-period job
  identity the scheduler (T016) uses for RQ enqueue, so a replayed or raced tick lands on
  the same job id and the per-period unique index is the second lock on the same door.

Timezone correctness is the point of FR-003: dates come from the REPORTING timezone, never
from UTC arithmetic. The Karachi case proves a UTC-date derivation would be wrong by a day;
the London cases prove the derivation stays wall-clock-correct across a DST fallback, where
the same local time exists twice in one calendar day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest


def _windows() -> tuple:
    """Deferred import — red for the right reason until T011 lands the module."""
    from procurepilot_api.modules.reports.schedules import (
        derive_weekly_window,
        next_run_after,
        period_idempotency_key,
    )

    return derive_weekly_window, next_run_after, period_idempotency_key


# --- derive_weekly_window ----------------------------------------------------


def test_weekly_window_is_the_prior_complete_week_in_utc() -> None:
    derive_weekly_window, _, _ = _windows()
    run_at = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)  # a Monday run
    assert derive_weekly_window(run_at=run_at, timezone_name="UTC") == (
        date(2026, 10, 12),
        date(2026, 10, 18),
    )


def test_weekly_window_uses_the_reporting_timezone_not_utc() -> None:
    """Asia/Karachi is UTC+5 with no DST: 20:30Z is already the next local day. A UTC-date
    derivation would hand the report the wrong week — this is the whole of FR-003."""
    derive_weekly_window, _, _ = _windows()
    run_at = datetime(2026, 10, 20, 20, 30, tzinfo=UTC)  # 2026-10-21 01:30 in Karachi
    assert derive_weekly_window(run_at=run_at, timezone_name="Asia/Karachi") == (
        date(2026, 10, 14),
        date(2026, 10, 20),
    )
    # The same instant under UTC derivation would be a different window — pinned so a
    # regression to UTC arithmetic cannot pass unnoticed.
    assert derive_weekly_window(run_at=run_at, timezone_name="UTC") == (
        date(2026, 10, 13),
        date(2026, 10, 19),
    )


def test_weekly_window_is_wall_clock_correct_across_a_dst_fallback() -> None:
    """Europe/London falls back at 2026-10-25 02:00 BST -> 01:00 GMT, so local 01:30 exists
    TWICE that day. A run half an hour before the rollback and a run half an hour after it
    are different instants with the same local wall-clock time — both must derive the same
    local date, and therefore the same prior week."""
    derive_weekly_window, _, _ = _windows()
    before_rollback = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 01:30 BST
    after_rollback = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 01:30 GMT
    for run_at in (before_rollback, after_rollback):
        assert derive_weekly_window(run_at=run_at, timezone_name="Europe/London") == (
            date(2026, 10, 18),
            date(2026, 10, 24),
        )


def test_weekly_window_is_exactly_seven_calendar_days() -> None:
    derive_weekly_window, _, _ = _windows()
    run_at = datetime(2026, 9, 15, 6, 0, tzinfo=UTC)
    period_start, period_end = derive_weekly_window(run_at=run_at, timezone_name="UTC")
    assert (period_end - period_start).days == 6  # inclusive dates, seven days total


def test_weekly_window_rejects_an_unknown_timezone() -> None:
    derive_weekly_window, _, _ = _windows()
    run_at = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)
    with pytest.raises(Exception, match="Mars/Olympus_Mons|not found|Unknown"):
        derive_weekly_window(run_at=run_at, timezone_name="Mars/Olympus_Mons")


# --- next_run_after ----------------------------------------------------------


def test_next_run_after_returns_the_next_weekday_at_local_midnight_utc() -> None:
    _, next_run_after, _ = _windows()
    after = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)  # a Wednesday
    assert next_run_after(weekday=0, after=after, timezone_name="UTC") == datetime(
        2026, 10, 19, 0, 0, tzinfo=UTC
    )


def test_next_run_after_converts_local_midnight_to_utc() -> None:
    _, next_run_after, _ = _windows()
    after = datetime(2026, 10, 14, 20, 30, tzinfo=UTC)  # already Thursday in Karachi
    assert next_run_after(weekday=0, after=after, timezone_name="Asia/Karachi") == (
        datetime(2026, 10, 18, 19, 0, tzinfo=UTC)  # Monday 00:00 +05:00
    )


def test_next_run_after_never_returns_the_instant_itself() -> None:
    """Strictly after: a schedule created ON its weekday after local midnight must not be
    due immediately — its first window is not complete yet (FR-003)."""
    _, next_run_after, _ = _windows()
    after = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)  # Monday, after midnight
    assert next_run_after(weekday=0, after=after, timezone_name="UTC") == datetime(
        2026, 10, 26, 0, 0, tzinfo=UTC
    )


def test_next_run_after_handles_every_weekday() -> None:
    _, next_run_after, _ = _windows()
    after = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)  # Wednesday
    expected = {
        0: datetime(2026, 10, 19, 0, 0, tzinfo=UTC),  # Mon
        1: datetime(2026, 10, 20, 0, 0, tzinfo=UTC),  # Tue
        2: datetime(2026, 10, 21, 0, 0, tzinfo=UTC),  # Wed (next week — strictly after)
        3: datetime(2026, 10, 15, 0, 0, tzinfo=UTC),  # Thu
        4: datetime(2026, 10, 16, 0, 0, tzinfo=UTC),  # Fri
        5: datetime(2026, 10, 17, 0, 0, tzinfo=UTC),  # Sat
        6: datetime(2026, 10, 18, 0, 0, tzinfo=UTC),  # Sun
    }
    for weekday, run_at in expected.items():
        assert next_run_after(weekday=weekday, after=after, timezone_name="UTC") == run_at


def test_next_run_after_rejects_an_out_of_range_weekday() -> None:
    _, next_run_after, _ = _windows()
    after = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        next_run_after(weekday=7, after=after, timezone_name="UTC")
    with pytest.raises(ValueError):
        next_run_after(weekday=-1, after=after, timezone_name="UTC")


# --- period_idempotency_key --------------------------------------------------


def test_period_key_is_deterministic_for_the_same_schedule_and_period() -> None:
    _, _, period_idempotency_key = _windows()
    schedule_id = uuid4()
    assert period_idempotency_key(
        schedule_id=schedule_id, period_start=date(2026, 10, 12)
    ) == period_idempotency_key(schedule_id=schedule_id, period_start=date(2026, 10, 12))


def test_period_key_separates_periods_and_schedules() -> None:
    _, _, period_idempotency_key = _windows()
    schedule_a, schedule_b = uuid4(), uuid4()
    key_a_w1 = period_idempotency_key(schedule_id=schedule_a, period_start=date(2026, 10, 12))
    key_a_w2 = period_idempotency_key(schedule_id=schedule_a, period_start=date(2026, 10, 19))
    key_b_w1 = period_idempotency_key(schedule_id=schedule_b, period_start=date(2026, 10, 12))
    assert len({key_a_w1, key_a_w2, key_b_w1}) == 3


def test_period_key_is_a_plain_queue_safe_string() -> None:
    """The key doubles as the RQ job id (T016), so it must be a bounded, whitespace-free
    ASCII string — no UUID-object or locale-dependent formatting surprises."""
    _, _, period_idempotency_key = _windows()
    key = period_idempotency_key(schedule_id=UUID(int=1), period_start=date(2026, 10, 12))
    assert isinstance(key, str)
    assert key == key.strip()
    assert key.isascii()
    assert len(key) <= 100
