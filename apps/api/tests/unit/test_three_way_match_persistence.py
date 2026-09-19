from __future__ import annotations

from uuid import UUID, uuid4

from procurepilot_api.modules.accounting.three_way_match_persistence import (
    persist_three_way_match,
)
from procurepilot_api.modules.accounting.three_way_match_service import (
    MatchDiscrepancy,
    ThreeWayMatchResult,
)


class FakeCursor:
    def __init__(self, connection: FakeConnection, *, row_factory: object = None) -> None:
        self.connection = connection
        self.row_factory = row_factory
        self.rows: list[object] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.connection.calls.append((query, params))
        if "INSERT INTO three_way_match" in query or "ON CONFLICT" in query:
            self.rows = [(self.connection.match_id,)]
        elif "SELECT id, discrepancy_type" in query:
            self.rows = self.connection.existing_discrepancies
        elif "SELECT id FROM three_way_match" in query:
            self.rows = (
                [(self.connection.existing_match_id,)]
                if self.connection.existing_match_id is not None
                else []
            )
        elif "UPDATE three_way_match" in query:
            self.rows = [(self.connection.existing_match_id,)]
        else:
            self.rows = []

    def fetchone(self) -> object:
        return self.rows.pop(0)

    def fetchall(self) -> list[object]:
        return self.rows


class FakeConnection:
    def __init__(
        self,
        existing_discrepancies: list[dict[str, object]] | None = None,
        existing_match_id: UUID | None = None,
    ) -> None:
        self.match_id = uuid4()
        self.existing_match_id = existing_match_id
        self.existing_discrepancies = existing_discrepancies or []
        self.calls: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **kwargs: object) -> FakeCursor:
        return FakeCursor(self, **kwargs)


TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORDER_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BILL_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
LINE_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _result(*discrepancies: MatchDiscrepancy, source_hash: str = "hash-1") -> ThreeWayMatchResult:
    return ThreeWayMatchResult(
        result="needs_review",
        order_id=ORDER_ID,
        invoice_id="provider-bill-1",
        ruleset_version="r3.3",
        discrepancies=discrepancies,
        source_ids=("provider-bill-1",),
        source_hash=source_hash,
    )


def test_persists_match_and_nulls_unavailable_evidence_without_transaction_control() -> None:
    connection = FakeConnection()
    outcome = persist_three_way_match(
        connection,
        TENANT_ID,
        _result(MatchDiscrepancy("quantity_variance", LINE_ID)),
        purchase_order_id=ORDER_ID,
        synced_bill_id=BILL_ID,
    )

    assert outcome.match_id == connection.match_id
    assert outcome.inserted_discrepancy_count == 1
    assert outcome.reopened_discrepancy_count == 0
    assert outcome.auto_resolved_discrepancy_count == 0
    match_params = next(
        params for query, params in connection.calls if "INSERT INTO three_way_match" in query
    )
    assert match_params[6:18] == (None,) * 12
    assert connection.commits == connection.rollbacks == 0
    assert all("tenant_id" in query.lower() for query, _params in connection.calls)


def test_no_bill_existing_match_update_uses_exact_parameter_order() -> None:
    existing_match_id = uuid4()
    connection = FakeConnection(existing_match_id=existing_match_id)
    evidence = {
        "ordered_quantity": "1",
        "confirmed_quantity": "2",
        "received_quantity": "3",
        "invoiced_quantity": "4",
        "ordered_unit_price_amount": "5",
        "ordered_unit_price_currency": "USD",
        "invoiced_unit_price_amount": "6",
        "invoiced_unit_price_currency": "EUR",
        "ordered_total_amount": "7",
        "ordered_total_currency": "GBP",
        "invoiced_total_amount": "8",
        "invoiced_total_currency": "CAD",
    }

    outcome = persist_three_way_match(
        connection,
        TENANT_ID,
        _result(),
        purchase_order_id=ORDER_ID,
        evidence=evidence,
    )

    update_params = next(
        params
        for query, params in connection.calls
        if query.lstrip().startswith("UPDATE three_way_match")
    )
    assert outcome.match_id == existing_match_id
    assert len(update_params) == 19
    assert update_params == (
        "needs_review",
        "r3.3",
        ORDER_ID,
        None,
        "1",
        "2",
        "3",
        "4",
        "5",
        "USD",
        "6",
        "EUR",
        "7",
        "GBP",
        "8",
        "CAD",
        "hash-1",
        TENANT_ID,
        existing_match_id,
    )


def test_changed_source_reopens_resolved_row_and_resolves_missing_open_row() -> None:
    resolved_id = uuid4()
    stale_id = uuid4()
    connection = FakeConnection(
        [
            {
                "id": resolved_id,
                "discrepancy_type": "quantity_variance",
                "purchase_order_id": ORDER_ID,
                "evidence": {"order_line_id": str(LINE_ID)},
                "source_hash": "old-hash",
                "status": "resolved",
            },
            {
                "id": stale_id,
                "discrepancy_type": "missing_receipt",
                "purchase_order_id": ORDER_ID,
                "evidence": {"order_line_id": None},
                "source_hash": "old-hash",
                "status": "open",
            },
        ]
    )

    outcome = persist_three_way_match(
        connection,
        TENANT_ID,
        _result(MatchDiscrepancy("quantity_variance", LINE_ID), source_hash="new-hash"),
        purchase_order_id=ORDER_ID,
        synced_bill_id=BILL_ID,
        evidence={"invoiced_quantity": "3"},
    )

    assert outcome.reopened_discrepancy_count == 1
    assert outcome.auto_resolved_discrepancy_count == 1
    update_queries = [
        query.lower()
        for query, _params in connection.calls
        if query.lstrip().lower().startswith("update")
    ]
    assert any("reopened_at" in query and "resolved_by" in query for query in update_queries)
    assert any(
        "status = 'resolved'" in query and "resolved_by = null" in query for query in update_queries
    )
