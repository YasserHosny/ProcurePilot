from datetime import UTC, datetime, timedelta

from procurepilot_api.modules.offers.freshness import freshness_projection


def test_offer_freshness_is_fresh_through_target_window() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)

    score, age_days, status, due_at = freshness_projection(
        now - timedelta(days=7), now=now, target_days=14
    )

    assert score == "0.5000"
    assert age_days == 7
    assert status == "fresh"
    assert due_at == now + timedelta(days=7)


def test_offer_freshness_marks_old_observation_stale_and_clamps_score() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)

    score, age_days, status, _ = freshness_projection(
        now - timedelta(days=21), now=now, target_days=14
    )

    assert score == "0.0000"
    assert age_days == 21
    assert status == "stale"
