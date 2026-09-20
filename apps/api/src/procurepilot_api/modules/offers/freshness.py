from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

FreshnessStatus = Literal["fresh", "stale"]


def freshness_projection(
    recorded_at: datetime,
    *,
    now: datetime | None = None,
    target_days: int = 14,
) -> tuple[str, int, FreshnessStatus, datetime]:
    """Return a deterministic score, age, status, and due time for an observed offer."""
    observed = recorded_at if recorded_at.tzinfo else recorded_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    age_seconds = max(0, (current - observed).total_seconds())
    age_days = int(age_seconds // 86_400)
    score = max(
        Decimal("0"),
        Decimal("1") - (Decimal(str(age_seconds)) / Decimal(target_days * 86_400)),
    )
    score = score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    status: FreshnessStatus = "fresh" if age_seconds <= target_days * 86_400 else "stale"
    return format(score, "f"), age_days, status, observed + timedelta(days=target_days)
