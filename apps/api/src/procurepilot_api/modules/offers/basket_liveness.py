"""Detects basket-split jobs that no solver worker is going to pick up.

The solver is a separate deployable (services/optimiser). If it is not running, a job stays
``queued`` forever and the UI would poll forever. A queued job is treated as stuck when it has
waited longer than ``basket_split_stall_seconds`` while no RQ worker is registered on the queue
(RQ workers heartbeat their own registration in Redis), or longer than
``basket_split_expiry_seconds`` regardless. A ``running`` job older than the expiry is a worker
that died mid-solve.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from procurepilot_api.config import Settings

StaleCode = Literal["optimiser_unavailable", "optimiser_timeout"]

STALE_MESSAGES: dict[StaleCode, str] = {
    "optimiser_unavailable": (
        "The optimisation service is not responding. Please try again shortly."
    ),
    "optimiser_timeout": "The optimisation did not finish in time. Please try again.",
}


def optimiser_worker_alive(settings: Settings) -> bool | None:
    """True/False when Redis answers; None when liveness cannot be determined."""
    try:
        from redis import Redis
        from rq import Worker

        connection = Redis.from_url(settings.redis_url)
        return any(
            settings.basket_split_queue_name in worker.queue_names()
            for worker in Worker.all(connection=connection)
        )
    except Exception:
        return None


def stale_code(
    *,
    status: str,
    created_at: datetime,
    started_at: datetime | None,
    now: datetime,
    stall_seconds: int,
    expiry_seconds: int,
    worker_alive: bool | None,
) -> StaleCode | None:
    if status == "queued":
        age = now - created_at
        if age > timedelta(seconds=expiry_seconds):
            return "optimiser_timeout"
        if worker_alive is False and age > timedelta(seconds=stall_seconds):
            return "optimiser_unavailable"
    elif status == "running" and started_at is not None:
        if now - started_at > timedelta(seconds=expiry_seconds):
            return "optimiser_timeout"
    return None
