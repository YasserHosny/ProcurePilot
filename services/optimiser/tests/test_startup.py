from __future__ import annotations

from procurepilot_optimiser_worker.__main__ import startup_message


def test_startup_message_names_queue_and_redis_host_without_credentials() -> None:
    message = startup_message("basket-split", "redis://user:s3cret@10.1.2.3:6379/0")
    assert "queue=basket-split" in message
    assert "redis=10.1.2.3:6379" in message
    assert "s3cret" not in message
