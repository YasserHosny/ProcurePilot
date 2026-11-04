"""The RFQ read interface names the one RFQ a quotation answered (P-153)."""

from __future__ import annotations

from uuid import UUID, uuid4

from procurepilot_api.modules.rfq.read_api import rfq_id_for_quotation_with_conn


class _Cursor:
    def __init__(self, rfq_ids: list[UUID]) -> None:
        self._rows = [{"rfq_id": rfq_id} for rfq_id in rfq_ids]
        self.params: object = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _sql: str, params: object = None) -> None:
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor

    def cursor(self, **_kwargs: object) -> _Cursor:
        return self.cursor_obj


def _lookup(rfq_ids: list[UUID]) -> tuple[UUID | None, _Cursor]:
    cursor = _Cursor(rfq_ids)
    quotation_id = uuid4()
    result = rfq_id_for_quotation_with_conn(_Connection(cursor), quotation_id)  # type: ignore[arg-type]
    assert cursor.params == (quotation_id,)
    return result, cursor


def test_a_quotation_that_answered_one_rfq_names_it() -> None:
    rfq_id = uuid4()
    assert _lookup([rfq_id])[0] == rfq_id


def test_the_same_rfq_twice_is_still_one_rfq() -> None:
    rfq_id = uuid4()
    assert _lookup([rfq_id, rfq_id])[0] == rfq_id


def test_a_quotation_that_answered_no_rfq_has_none() -> None:
    assert _lookup([])[0] is None


def test_a_quotation_mapped_to_several_rfqs_is_not_guessed() -> None:
    assert _lookup([uuid4(), uuid4()])[0] is None
