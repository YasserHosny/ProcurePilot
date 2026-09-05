from __future__ import annotations

from uuid import UUID, uuid4

from procurepilot_extraction_worker.models import ExtractedField, ExtractionResult
from procurepilot_extraction_worker.worker import SupplierMatch, _match_supplier, _review_reason


def test_supplier_match_returns_high_confidence_supplier() -> None:
    supplier_id = uuid4()
    conn = _FakeConnection((supplier_id, 0.81234))

    match = _match_supplier(
        conn,
        uuid4(),
        {"supplier_name": ExtractedField("supplier_name", "Fresh Farms Ltd", 0.99)},
    )

    assert match == SupplierMatch(supplier_id, 0.812, had_candidates=True)


def test_low_confidence_supplier_candidate_flags_no_supplier_match_reason() -> None:
    conn = _FakeConnection((uuid4(), 0.21))

    match = _match_supplier(
        conn,
        uuid4(),
        {"supplier_name": ExtractedField("supplier_name", "Unknown Vendor", 0.99)},
    )

    assert match == SupplierMatch(None, 0.21, had_candidates=True)
    assert _review_reason(_result(), "reconciled", 0.85, match) == "no_supplier_match"


def test_zero_supplier_candidates_does_not_flag_no_supplier_match_reason() -> None:
    conn = _FakeConnection(None)

    match = _match_supplier(
        conn,
        uuid4(),
        {"supplier_name": ExtractedField("supplier_name", "Fresh Farms Ltd", 0.99)},
    )

    assert match == SupplierMatch(None, None, had_candidates=False)
    assert _review_reason(_result(), "reconciled", 0.85, match) is None


def test_missing_supplier_name_does_not_flag_no_supplier_match_reason() -> None:
    match = _match_supplier(_FakeConnection((uuid4(), 0.9)), uuid4(), {})

    assert match == SupplierMatch(None, None, had_candidates=False)
    assert _review_reason(_result(), "reconciled", 0.85, match) is None


def _result() -> ExtractionResult:
    return ExtractionResult(
        method="structured_parse",
        model_version="test",
        header={"currency": ExtractedField("currency", "GBP", 1.0)},
        lines=[],
        stated_total=None,
    )


class _FakeConnection:
    def __init__(self, row: tuple[UUID, float] | None) -> None:
        self.row = row
        self.executed_params: tuple[object, ...] | None = None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _query: str, params: tuple[object, ...]) -> None:
        self._conn.executed_params = params

    def fetchone(self) -> tuple[UUID, float] | None:
        return self._conn.row
