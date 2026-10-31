from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from procurepilot_api.modules.offers import basket_service
from procurepilot_api.modules.offers.basket_liveness import stale_code

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def _code(
    status: str, age: int, *, alive: bool | None, started_age: int | None = None
) -> str | None:
    return stale_code(
        status=status,
        created_at=NOW - timedelta(seconds=age),
        started_at=NOW - timedelta(seconds=started_age) if started_age is not None else None,
        now=NOW,
        stall_seconds=60,
        expiry_seconds=900,
        worker_alive=alive,
    )


def test_fresh_queued_job_is_not_stale() -> None:
    assert _code("queued", 30, alive=False) is None


def test_queued_past_stall_with_no_worker_is_unavailable() -> None:
    assert _code("queued", 61, alive=False) == "optimiser_unavailable"


def test_queued_past_stall_with_live_worker_keeps_waiting() -> None:
    assert _code("queued", 300, alive=True) is None


def test_queued_with_unknown_liveness_waits_for_expiry() -> None:
    assert _code("queued", 300, alive=None) is None
    assert _code("queued", 901, alive=None) == "optimiser_timeout"


def test_queued_past_expiry_times_out_even_with_live_worker() -> None:
    assert _code("queued", 901, alive=True) == "optimiser_timeout"


def test_running_job_times_out_after_expiry() -> None:
    assert _code("running", 2000, alive=True, started_age=100) is None
    assert _code("running", 2000, alive=True, started_age=901) == "optimiser_timeout"


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_terminal_jobs_are_never_stale(status: str) -> None:
    assert _code(status, 99999, alive=False) is None


class _Cursor:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.conn.statements.append(sql)

    def fetchone(self) -> dict[str, object]:
        return self.conn.row


class _Conn:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.statements: list[str] = []

    def cursor(self, **_: object) -> _Cursor:
        return _Cursor(self)


def test_get_job_reports_unreachable_optimiser_as_failed_with_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid4()
    row = {
        "id": job_id,
        "supplier_ids": [uuid4(), uuid4()],
        "items": [],
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": datetime.now(UTC) - timedelta(seconds=120),
        "started_at": None,
        "completed_at": None,
    }
    conn = _Conn(row)

    @contextmanager
    def fake_db(*_: object) -> Iterator[_Conn]:
        yield conn

    monkeypatch.setattr(basket_service, "_authenticated_db", fake_db)
    monkeypatch.setattr(basket_service, "optimiser_worker_alive", lambda _s: False)
    service = basket_service.BasketService.__new__(basket_service.BasketService)
    service._settings = type(
        "S", (), {"basket_split_stall_seconds": 60, "basket_split_expiry_seconds": 900}
    )()

    job = service.get_job(member=None, job_id=job_id)  # type: ignore[arg-type]

    assert job.status == "failed"
    assert job.error is not None and job.error["code"] == "optimiser_unavailable"
    assert any("update basket_split_job" in s for s in conn.statements)


def test_requeueing_a_failed_job_restarts_the_expiry_clock() -> None:
    job_id = uuid4()
    conn = _Conn({"id": job_id, "status": "queued"})

    row = basket_service._requeue_failed_job(conn, job_id)  # type: ignore[arg-type]

    sql = " ".join(conn.statements)
    assert "created_at = now()" in sql
    assert "started_at = null" in sql
    assert row["status"] == "queued"


def test_each_attempt_gets_its_own_token_and_rq_job_id() -> None:
    from procurepilot_api.modules.offers.basket_liveness import attempt_token, rq_job_id

    job_id = uuid4()
    first = {"id": job_id, "created_at": NOW}
    retry = {"id": job_id, "created_at": NOW + timedelta(seconds=1)}

    assert attempt_token(first) != attempt_token(retry)
    assert rq_job_id(first) != rq_job_id(retry)
    assert rq_job_id(first).startswith(str(job_id))


def test_enqueue_payload_carries_the_attempt_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import redis
    import rq

    captured: dict[str, object] = {}

    class FakeQueue:
        def __init__(self, *_: object, **__: object) -> None: ...

        def enqueue(self, func: str, payload: dict[str, object], job_id: str) -> None:
            captured.update(payload=payload, job_id=job_id)

    monkeypatch.setattr(rq, "Queue", FakeQueue)
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda *_: object()))
    job_id = uuid4()
    row = {"id": job_id, "created_at": NOW, "request_snapshot": None}
    member = type("M", (), {"tenant_id": uuid4()})()
    settings = type("S", (), {"basket_split_queue_name": "q", "redis_url": "redis://x"})()

    basket_service._enqueue_redis_job(settings, row, member)  # type: ignore[arg-type]

    assert captured["payload"]["attempt"] == NOW.isoformat()  # type: ignore[index]
    assert captured["job_id"] != str(job_id)
    assert str(captured["job_id"]).startswith(str(job_id))


def test_failed_enqueue_logs_the_cause_and_not_the_redis_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import redis
    from redis.exceptions import AuthenticationError

    from procurepilot_api.errors import ServiceUnavailableError

    def refuse(*_: object) -> object:
        raise AuthenticationError("AUTH called without any password configured")

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(refuse))
    job_id = uuid4()
    row = {"id": job_id, "created_at": NOW, "request_snapshot": None}
    member = type("M", (), {"tenant_id": uuid4()})()
    url = "redis://:s3cret@203.0.113.9:6379/0"
    settings = type("S", (), {"basket_split_queue_name": "q", "redis_url": url})()

    with caplog.at_level("ERROR"), pytest.raises(ServiceUnavailableError):
        basket_service._enqueue_redis_job(settings, row, member)  # type: ignore[arg-type]

    assert "AuthenticationError" in caplog.text
    assert "AUTH called without any password configured" in caplog.text
    assert str(job_id) in caplog.text
    assert "s3cret" not in caplog.text
