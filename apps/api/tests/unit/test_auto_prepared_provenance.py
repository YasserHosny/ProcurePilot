"""Finding 38a/38b: guardrail provenance on purchase requests, and the worker's cost-centre
fallback, without a database."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from procurepilot_api.modules.ingestion.orchestrator import _guardrail_cost_centre
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.modules.rfq.guardrails import AutoPreparationGuardrail


class _Query:
    def __init__(self, client: _Client, name: str, rows: list[dict[str, Any]]) -> None:
        self.client, self.name, self.rows = client, name, rows

    def select(self, _columns: str) -> _Query:
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self.client.calls.append((self.name, column, sorted(values)))
        self.rows = [row for row in self.rows if str(row[column]) in set(values)]
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class _Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.calls: list[tuple[str, str, list[str]]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name, list(self.tables.get(name, [])))


def test_provenance_is_batched_and_names_the_winning_supplier() -> None:
    prepared, manual_from_rfq, manual = str(uuid4()), str(uuid4()), str(uuid4())
    guardrail_id, rfq_id, supplier_id = uuid4(), uuid4(), uuid4()
    created_at = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    client = _Client(
        {
            "auto_preparation_event": [
                {
                    "purchase_request_id": prepared,
                    "guardrail_id": str(guardrail_id),
                    "rfq_id": str(rfq_id),
                    "supplier_id": str(supplier_id),
                    "created_at": created_at.isoformat(),
                }
            ],
            "supplier": [{"id": str(supplier_id), "name": "مخبز النور"}],
        }
    )
    rows = [
        {"id": prepared, "source_rfq_response_id": str(uuid4())},
        {"id": manual_from_rfq, "source_rfq_response_id": str(uuid4())},
        {"id": manual, "source_rfq_response_id": None},
    ]

    result = RequestsService.__new__(RequestsService)._fetch_auto_prepared_batch(client, rows)

    assert set(result) == {prepared}
    provenance = result[prepared]
    assert (provenance.guardrail_id, provenance.rfq_id, provenance.supplier_id) == (
        guardrail_id,
        rfq_id,
        supplier_id,
    )
    assert provenance.supplier_name == "مخبز النور"
    assert provenance.created_at == created_at
    # One query per table for the whole page; a request never prepared from an RFQ response
    # is not even asked about.
    assert client.calls == [
        ("auto_preparation_event", "purchase_request_id", sorted([prepared, manual_from_rfq])),
        ("supplier", "id", [str(supplier_id)]),
    ]


def test_requests_without_an_rfq_source_cost_no_query() -> None:
    client = _Client({})
    rows = [{"id": str(uuid4()), "source_rfq_response_id": None}]
    assert RequestsService.__new__(RequestsService)._fetch_auto_prepared_batch(client, rows) == {}
    assert client.calls == []


class _Cursor:
    def __init__(self, row: object) -> None:
        self.row, self.executed = row, []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> object:
        return self.row


def _guardrail(cost_centre_id: UUID | None) -> AutoPreparationGuardrail:
    return AutoPreparationGuardrail(
        id=uuid4(),
        tenant_id=uuid4(),
        enabled=True,
        min_response_count=1,
        max_order_value_amount=1,
        max_order_value_currency="EGP",
        max_price_variance_pct=0,
        supplier_allowlist=None,
        category_allowlist=None,
        default_branch_id=uuid4(),
        created_by_membership_id=uuid4(),
        default_cost_centre_id=cost_centre_id,
    )


def test_worker_uses_the_cost_centre_only_while_it_is_still_valid() -> None:
    cost_centre_id = uuid4()
    guardrail = _guardrail(cost_centre_id)

    valid = _Cursor({"?column?": 1})
    assert _guardrail_cost_centre(valid, tenant_id=guardrail.tenant_id, guardrail=guardrail) == (
        cost_centre_id
    )
    sql, params = valid.executed[0]
    assert "branch_id = %s" in sql and "not is_archived" in sql
    assert params == (guardrail.tenant_id, cost_centre_id, guardrail.default_branch_id)

    stale = _Cursor(None)  # archived since, or moved to another branch
    assert _guardrail_cost_centre(stale, tenant_id=guardrail.tenant_id, guardrail=guardrail) is None

    none = _Cursor(None)
    assert _guardrail_cost_centre(none, tenant_id=uuid4(), guardrail=_guardrail(None)) is None
    assert none.executed == []
