from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.modules.devices import push_job


class _Secret:
    def get_secret_value(self) -> str:
        return "postgresql://unit-test"


class _Settings:
    database_url = _Secret()


class _Connection:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def _wire_job(
    monkeypatch: pytest.MonkeyPatch,
    *,
    notification: dict[str, object],
    registrations: list[dict[str, object]],
    send_result: bool | Exception,
) -> tuple[_Connection, list[tuple[dict[str, object], dict[str, str]]], list[str]]:
    conn = _Connection()
    send_calls: list[tuple[dict[str, object], dict[str, str]]] = []
    marked_statuses: list[str] = []

    monkeypatch.setattr(push_job, "get_settings", lambda: _Settings())
    monkeypatch.setattr(push_job.psycopg, "connect", lambda _dsn: conn)
    monkeypatch.setattr(
        push_job,
        "_notification_row",
        lambda _conn, notification_id: (
            notification if notification_id == notification["id"] else None
        ),
    )
    monkeypatch.setattr(
        push_job,
        "_device_registrations",
        lambda _conn, _notification: registrations,
    )

    def fake_send(
        registration: dict[str, object], payload: dict[str, str]
    ) -> bool:
        send_calls.append((registration, payload))
        if isinstance(send_result, Exception):
            raise send_result
        return send_result

    monkeypatch.setattr(push_job, "_send_to_device", fake_send)
    monkeypatch.setattr(
        push_job,
        "_mark_attempted",
        lambda _conn, _notification_id, *, status: marked_statuses.append(status),
    )
    return conn, send_calls, marked_statuses


def _notification() -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "purchase_request_id": uuid4(),
        "member_id": uuid4(),
    }


def _registration(member_id: object) -> dict[str, object]:
    return {
        "id": uuid4(),
        "member_id": member_id,
        "platform": "ios",
        "push_token": f"tok-{uuid4()}",
    }


def test_process_push_notification_fans_out_to_every_current_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notification = _notification()
    registrations = [
        _registration(notification["member_id"]),
        _registration(notification["member_id"]),
        _registration(notification["member_id"]),
    ]
    conn, send_calls, marked_statuses = _wire_job(
        monkeypatch,
        notification=notification,
        registrations=registrations,
        send_result=True,
    )

    push_job.process_push_notification(notification["id"])

    assert [call[0]["id"] for call in send_calls] == [
        registration["id"] for registration in registrations
    ]
    assert {call[1]["notification_id"] for call in send_calls} == {
        str(notification["id"])
    }
    assert marked_statuses == ["sent"]
    assert conn.commits == 1


def test_process_push_notification_marks_sent_without_attempting_send_when_no_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notification = _notification()
    conn, send_calls, marked_statuses = _wire_job(
        monkeypatch,
        notification=notification,
        registrations=[],
        send_result=False,
    )

    push_job.process_push_notification(notification["id"])

    assert send_calls == []
    assert marked_statuses == ["sent"]
    assert conn.commits == 1


def test_process_push_notification_marks_failed_when_all_real_registration_sends_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notification = _notification()
    registrations = [
        _registration(notification["member_id"]),
        _registration(notification["member_id"]),
    ]
    conn, send_calls, marked_statuses = _wire_job(
        monkeypatch,
        notification=notification,
        registrations=registrations,
        send_result=False,
    )

    push_job.process_push_notification(notification["id"])

    assert [call[0]["id"] for call in send_calls] == [
        registration["id"] for registration in registrations
    ]
    assert marked_statuses == ["failed"]
    assert conn.commits == 1


def test_process_push_notification_logs_send_exceptions_and_continues_to_next_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notification = _notification()
    registrations = [
        _registration(notification["member_id"]),
        _registration(notification["member_id"]),
    ]
    conn = _Connection()
    send_calls: list[object] = []
    marked_statuses: list[str] = []

    monkeypatch.setattr(push_job, "get_settings", lambda: _Settings())
    monkeypatch.setattr(push_job.psycopg, "connect", lambda _dsn: conn)
    monkeypatch.setattr(push_job, "_notification_row", lambda *_args: notification)
    monkeypatch.setattr(
        push_job,
        "_device_registrations",
        lambda *_args: registrations,
    )

    def flaky_send(
        registration: dict[str, object], _payload: dict[str, str]
    ) -> bool:
        send_calls.append(registration["id"])
        if len(send_calls) == 1:
            raise RuntimeError("provider timeout")
        return False

    monkeypatch.setattr(push_job, "_send_to_device", flaky_send)
    monkeypatch.setattr(
        push_job,
        "_mark_attempted",
        lambda _conn, _notification_id, *, status: marked_statuses.append(status),
    )

    push_job.process_push_notification(notification["id"])

    assert send_calls == [registration["id"] for registration in registrations]
    assert marked_statuses == ["failed"]
    assert conn.commits == 1
