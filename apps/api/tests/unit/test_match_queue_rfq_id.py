"""The queue says which RFQ a quotation answered, so «Compare responses» can open it (P-153, PPS-197)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.matching import service as matching_service_module
from procurepilot_api.modules.matching.service import MatchingService


class _Cursor:
    def __init__(self, rfq_id: UUID | None) -> None:
        self._rfq_id = rfq_id
        self.sql: list[str] = []
        self._last: list[dict[str, object]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        self.sql.append(sql)
        if "rfq_recipient" in sql:
            self._last = [{"rfq_id": self._rfq_id}] if self._rfq_id else []
        else:
            self._last = []  # the queue itself is empty: every line of the quote is matched

    def fetchall(self) -> list[dict[str, object]]:
        return self._last

    def fetchone(self) -> dict[str, object] | None:
        return self._last[0] if self._last else None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self, **_kwargs: object) -> _Cursor:
        return self._cursor


def _service(monkeypatch: pytest.MonkeyPatch, rfq_id: UUID | None) -> tuple[MatchingService, _Cursor]:
    cursor = _Cursor(rfq_id)

    @contextmanager
    def db(_settings: object, _member: object) -> Iterator[_Connection]:
        yield _Connection(cursor)

    monkeypatch.setattr(matching_service_module, "_authenticated_db", db)
    return MatchingService(), cursor


def _member() -> SimpleNamespace:
    return SimpleNamespace(tenant_id=uuid4())


def test_a_quotation_scoped_queue_names_the_rfq_it_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    rfq_id = uuid4()
    service, _ = _service(monkeypatch, rfq_id)

    result = service.list_match_tasks(
        bearer_token="t", member=_member(), quotation_id=uuid4(), status="open"
    )

    assert result.items == []
    assert result.rfq_id == rfq_id


def test_a_quotation_that_answered_no_rfq_has_no_rfq_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _service(monkeypatch, None)

    result = service.list_match_tasks(
        bearer_token="t", member=_member(), quotation_id=uuid4(), status="open"
    )

    assert result.rfq_id is None


def test_the_workspace_wide_queue_does_not_look_up_an_rfq(monkeypatch: pytest.MonkeyPatch) -> None:
    service, cursor = _service(monkeypatch, uuid4())

    result = service.list_match_tasks(bearer_token="t", member=_member(), status="open")

    assert result.rfq_id is None
    assert not any("rfq_recipient" in sql for sql in cursor.sql)
