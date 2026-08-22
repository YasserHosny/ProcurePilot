from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.workers import export_worker


def test_worker_callable_and_payload_shape() -> None:
    assert callable(export_worker.process_export_job)
    payload = {"job_id": str(uuid4()), "tenant_id": str(uuid4())}

    assert set(payload) == {"job_id", "tenant_id"}


def test_worker_main_uses_configured_exports_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Redis:
        @staticmethod
        def from_url(url: str) -> str:
            captured["redis_url"] = url
            return "redis"

    class _Worker:
        def __init__(self, queues: list[str], *, connection: object) -> None:
            captured["queues"] = queues
            captured["connection"] = connection

        def work(self) -> None:
            captured["worked"] = True

    class _Settings:
        export_queue_name = "exports"
        redis_url = "redis://localhost:6379/0"

    monkeypatch.setattr("redis.Redis", _Redis)
    monkeypatch.setattr("rq.Worker", _Worker)
    monkeypatch.setattr(export_worker, "get_settings", lambda: _Settings())

    export_worker.main()

    assert captured == {
        "redis_url": "redis://localhost:6379/0",
        "queues": ["exports"],
        "connection": "redis",
        "worked": True,
    }
