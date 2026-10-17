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


def test_current_offer_validation_rejects_products_without_supplier_offers() -> None:
    from procurepilot_api.errors import UnprocessableEntityError

    product_id = uuid4()

    class OfferCursor(_Cursor):
        def fetchall(self) -> list[tuple[object, ...]]:
            return []

    class OfferConn(_Conn):
        def cursor(self, **_: object) -> OfferCursor:
            return OfferCursor(self)

    conn = OfferConn({})
    payload = type(
        "Payload",
        (),
        {
            "items": [type("Item", (), {"workspace_product_id": product_id})()],
            "supplier_ids": [uuid4(), uuid4()],
        },
    )()

    with pytest.raises(UnprocessableEntityError) as exc_info:
        basket_service._ensure_current_offers(conn, payload)  # type: ignore[arg-type]

    assert exc_info.value.details == {
        "reason": "no_offers_for_products",
        "product_ids": [str(product_id)],
    }
    assert "valid_to" in conn.statements[0]


def test_create_job_does_not_enqueue_when_offer_check_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import contextmanager
    from unittest.mock import Mock

    from procurepilot_api.errors import UnprocessableEntityError

    @contextmanager
    def fake_db(*_: object) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(basket_service, "_authenticated_db", fake_db)
    monkeypatch.setattr(basket_service, "_visible_suppliers", lambda *_args: None)
    monkeypatch.setattr(basket_service, "_visible_products", lambda *_args: None)
    monkeypatch.setattr(
        basket_service,
        "_ensure_current_offers",
        lambda *_args: (_ for _ in ()).throw(
            UnprocessableEntityError(
                details={"reason": "no_offers_for_products", "product_ids": []}
            )
        ),
    )
    enqueue_job = Mock()
    monkeypatch.setattr(basket_service, "_enqueue_redis_job", enqueue_job)
    service = basket_service.BasketService.__new__(basket_service.BasketService)
    service._settings = object()
    monkeypatch.setattr(service, "_expire_stuck_jobs", lambda _conn: None)

    payload = type(
        "Payload",
        (),
        {"supplier_ids": [], "items": []},
    )()
    with pytest.raises(UnprocessableEntityError):
        service.create_job(member=object(), payload=payload)  # type: ignore[arg-type]

    enqueue_job.assert_not_called()


def test_idempotent_replay_skips_current_offer_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    job_id = uuid4()
    conn = _Conn(
        {
            "id": job_id,
            "supplier_ids": [uuid4(), uuid4()],
            "items": [],
            "status": "completed",
            "created_at": datetime.now(UTC),
        }
    )

    @contextmanager
    def fake_db(*_: object) -> Iterator[_Conn]:
        yield conn

    check_offers = Mock(side_effect=AssertionError("Replay must not validate current offers"))
    monkeypatch.setattr(basket_service, "_authenticated_db", fake_db)
    monkeypatch.setattr(basket_service, "_ensure_current_offers", check_offers)
    service = basket_service.BasketService.__new__(basket_service.BasketService)
    service._settings = object()

    job, created = service.create_job(
        member=SimpleNamespace(tenant_id=uuid4()),  # type: ignore[arg-type]
        payload=object(),  # type: ignore[arg-type]
        idempotency_key=uuid4(),
    )

    assert job.id == job_id
    assert created is False
    check_offers.assert_not_called()
