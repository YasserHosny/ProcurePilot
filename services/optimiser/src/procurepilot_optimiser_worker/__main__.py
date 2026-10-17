from __future__ import annotations

import logging
from urllib.parse import urlsplit

from redis import Redis
from rq import Worker

from procurepilot_optimiser_worker.settings import get_settings

logger = logging.getLogger("procurepilot_optimiser_worker")


def startup_message(queue_name: str, redis_url: str) -> str:
    """One greppable line for the bunny.net logs; never includes credentials."""
    parts = urlsplit(redis_url)
    return f"optimiser worker starting: queue={queue_name} redis={parts.hostname}:{parts.port}"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    logger.info(startup_message(settings.queue_name, settings.redis_url))
    connection = Redis.from_url(settings.redis_url)
    connection.ping()  # fail fast and loudly if the hosted Redis is unreachable
    worker = Worker([settings.queue_name], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
