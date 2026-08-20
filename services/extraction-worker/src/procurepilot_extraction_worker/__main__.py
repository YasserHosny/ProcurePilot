from __future__ import annotations

from redis import Redis
from rq import Worker

from procurepilot_extraction_worker.settings import get_settings


def main() -> None:
    settings = get_settings()
    worker = Worker([settings.queue_name], connection=Redis.from_url(settings.redis_url))
    worker.work()


if __name__ == "__main__":
    main()
