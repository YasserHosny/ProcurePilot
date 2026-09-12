from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.devices import push_job


class _Secret:
    def get_secret_value(self) -> str:
        return "postgresql://unit-test"


class _Settings:
    database_url = _Secret()
    redis_url = "redis://unit-test"


class _Connection:
    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _wire_sweep(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
) -> list[tuple[_Settings, UUID]]:
    enqueued: list[tuple[_Settings, UUID]] = []
    monkeypatch.setattr(push_job, "get_settings", lambda: _Settings())
    monkeypatch.setattr(push_job.psycopg, "connect", lambda _dsn: _Connection())
    monkeypatch.setattr(push_job, "_stale_notifications", lambda _conn, *, cutoff: rows)
    monkeypatch.setattr(
        push_job,
        "enqueue_push_job",
        lambda settings, notification_id: enqueued.append((settings, notification_id)),
    )
    return enqueued


def test_sweep_reenqueues_only_rows_selected_by_the_stale_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_id = uuid4()
    failed_id = uuid4()
    sent_id = uuid4()
    exhausted_id = uuid4()

    # `_stale_notifications` owns the SQL filters for status, age, and attempts. At unit level,
    # sweep_stale_push_notifications should enqueue exactly the rows that helper selected.
    selected_rows = [{"id": queued_id}, {"id": failed_id}]
    enqueued = _wire_sweep(monkeypatch, selected_rows)

    count = push_job.sweep_stale_push_notifications()

    assert count == 2
    assert [notification_id for _settings, notification_id in enqueued] == [
        queued_id,
        failed_id,
    ]
    assert sent_id not in {notification_id for _settings, notification_id in enqueued}
    assert exhausted_id not in {notification_id for _settings, notification_id in enqueued}


def test_sweep_enqueue_failure_for_one_row_does_not_stop_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id = uuid4()
    failing_id = uuid4()
    last_id = uuid4()
    enqueued: list[UUID] = []

    monkeypatch.setattr(push_job, "get_settings", lambda: _Settings())
    monkeypatch.setattr(push_job.psycopg, "connect", lambda _dsn: _Connection())
    monkeypatch.setattr(
        push_job,
        "_stale_notifications",
        lambda _conn, *, cutoff: [
            {"id": first_id},
            {"id": failing_id},
            {"id": last_id},
        ],
    )

    def enqueue(_settings: _Settings, notification_id: UUID) -> None:
        if notification_id == failing_id:
            raise RuntimeError("redis unavailable")
        enqueued.append(notification_id)

    monkeypatch.setattr(push_job, "enqueue_push_job", enqueue)

    count = push_job.sweep_stale_push_notifications()

    assert count == 2
    assert enqueued == [first_id, last_id]
