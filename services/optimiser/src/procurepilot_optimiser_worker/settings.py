from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerSettings:
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "basket-split"


def get_settings() -> WorkerSettings:
    return WorkerSettings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
        ),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        queue_name=os.environ.get("BASKET_SPLIT_QUEUE_NAME", "basket-split"),
    )
