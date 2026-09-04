from __future__ import annotations

from procurepilot_logging import configure_logging
from redis import Redis
from rq import Worker

from procurepilot_extraction_worker.settings import get_settings


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = Worker([settings.queue_name], connection=Redis.from_url(settings.redis_url))
    worker.work()


if __name__ == "__main__":
    main()
