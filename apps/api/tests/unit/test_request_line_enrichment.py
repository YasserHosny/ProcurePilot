from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestLineInput,
)
from procurepilot_api.modules.requests.service import RequestsService, _purchase_request_line
from procurepilot_api.modules.requests.valuation import LineEstimate


class RecordingSelectQuery:
    def __init__(
        self, table_name: str, rows: list[dict[str, object]], tracker: list[dict[str, object]]
    ) -> None:
        self.table_name = table_name
        self.rows = rows
        self.tracker = tracker
        self.filters: list[tuple[str, str]] = []
        self.in_filters: list[tuple[str, list[str]]] = []
        self.orders: list[tuple[str, bool]] = []
        self.inserts: list[dict[str, object]] | None = None

    def select(self, columns: str) -> RecordingSelectQuery:
        self.tracker.append({"table": self.table_name, "op": "select", "columns": columns})
        return self

    def eq(self, column: str, value: str) -> RecordingSelectQuery:
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[str]) -> RecordingSelectQuery:
        self.in_filters.append((column, values))
        self.tracker.append(
            {"table": self.table_name, "op": "in_", "column": column, "values": values}
        )
        return self

    def insert(self, rows: list[dict[str, object]]) -> RecordingSelectQuery:
        self.inserts = rows
        self.tracker.append({"table": self.table_name, "op": "insert", "rows": rows})
        return self

    def order(self, column: str, *, desc: bool = False) -> RecordingSelectQuery:
        self.orders.append((column, desc))
        return self

    def execute(self) -> SimpleNamespace:
        if self.inserts is not None:
            return SimpleNamespace(data=self.inserts)
        data = self.rows
        for col, val in self.filters:
            data = [r for r in data if str(r.get(col)) == val]
        for col, vals in self.in_filters:
            allowed = set(vals)
            data = [r for r in data if str(r.get(col)) in allowed]
        for col, desc in reversed(self.orders):
            data = sorted(data, key=lambda r: str(r.get(col, "")), reverse=desc)
        return SimpleNamespace(data=data)


class FakeEnrichmentClient:
    def __init__(
        self,
        *,
        line_rows: list[dict[str, object]],
        product_rows: list[dict[str, object]],
        pack_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.line_rows = line_rows
        self.product_rows = product_rows
        self.pack_rows = pack_rows or []
        self.query_log: list[dict[str, object]] = []

    def table(self, name: str) -> RecordingSelectQuery:
        if name == "purchase_request_line":
            return RecordingSelectQuery(name, self.line_rows, self.query_log)
        if name == "workspace_product":
            return RecordingSelectQuery(name, self.product_rows, self.query_log)
        if name == "pack_definition":
            return RecordingSelectQuery(name, self.pack_rows, self.query_log)
        return RecordingSelectQuery(name, [], self.query_log)


def test_line_enrichment_one_batched_query_and_maps_fields() -> None:
    req_id = str(uuid4())
    product_id_1 = str(uuid4())
    product_id_2 = str(uuid4())
    missing_product_id = str(uuid4())

    line_1 = {
        "id": str(uuid4()),
        "purchase_request_id": req_id,
        "workspace_product_id": product_id_1,
        "quantity": "2.000000",
        "pack_base_quantity": "6.000000",
        "quantity_received": None,
        "note": "Line 1",
        "estimated_unit_price_amount": "25.00",
        "estimated_unit_price_currency": "USD",
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    line_2 = {
        "id": str(uuid4()),
        "purchase_request_id": req_id,
        "workspace_product_id": product_id_2,
        "quantity": "5.000000",
        "pack_base_quantity": None,
        "quantity_received": None,
        "note": "Line 2",
        "estimated_unit_price_amount": "10.00",
        "estimated_unit_price_currency": "USD",
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    line_missing = {
        "id": str(uuid4()),
        "purchase_request_id": req_id,
        "workspace_product_id": missing_product_id,
        "quantity": "1.000000",
        "pack_base_quantity": "3.000000",
        "quantity_received": None,
        "note": "Missing product line",
        "estimated_unit_price_amount": None,
        "estimated_unit_price_currency": None,
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }

    # Live catalogue packs differ from the line snapshots and must not affect reads.
    product_1_data = {
        "id": product_id_1,
        "tenant_name": "Full Cream Milk",
        "canonical_product": {"base_unit": "litre"},
        "pack_definition": [
            {
                "id": str(uuid4()),
                "created_at": "2026-09-01T00:00:00Z",
                "base_quantity": "6.000000",
            },
            {
                "id": str(uuid4()),
                "created_at": "2026-09-15T00:00:00Z",
                "base_quantity": "18.000000",
            },
            {
                "id": str(uuid4()),
                "created_at": "2026-09-10T00:00:00Z",
                "base_quantity": "12.000000",
            },
        ],
    }

    tie_date = "2026-09-10T12:00:00Z"
    pack_low_id = "00000000-0000-0000-0000-000000000001"
    pack_high_id = "00000000-0000-0000-0000-000000000009"
    product_2_data = {
        "id": product_id_2,
        "tenant_name": "Sugar 1kg",
        "canonical_product": {"base_unit": "kilogram"},
        "pack_definition": [
            {
                "id": pack_low_id,
                "created_at": tie_date,
                "base_quantity": "5.000000",
            },
            {
                "id": pack_high_id,
                "created_at": tie_date,
                "base_quantity": "25.000000",
            },
        ],
    }

    client = FakeEnrichmentClient(
        line_rows=[line_1, line_2, line_missing],
        product_rows=[product_1_data, product_2_data],
    )

    service = RequestsService()
    batch = service._fetch_lines_batch(client, [req_id])

    # Exactly one batched query for workspace_product
    wp_selects = [
        q for q in client.query_log if q["table"] == "workspace_product" and q["op"] == "select"
    ]
    assert len(wp_selects) == 1, f"Expected 1 workspace_product select query, got {len(wp_selects)}"
    assert "pack_definition" not in wp_selects[0]["columns"]
    assert not any(q["table"] == "pack_definition" for q in client.query_log)
    line_select = next(q for q in client.query_log if q["table"] == "purchase_request_line")
    assert "pack_base_quantity" in line_select["columns"]

    wp_in_filters = [
        q for q in client.query_log if q["table"] == "workspace_product" and q["op"] == "in_"
    ]
    assert len(wp_in_filters) == 1
    queried_ids = set(wp_in_filters[0]["values"])
    assert queried_ids == {product_id_1, product_id_2, missing_product_id}

    lines = batch[req_id]
    assert len(lines) == 3

    # Map to schema models
    model_lines = [_purchase_request_line(r) for r in lines]

    # Snapshot survives a changed live pack.
    assert model_lines[0].product_name == "Full Cream Milk"
    assert model_lines[0].base_unit == "litre"
    assert model_lines[0].pack_base_quantity == "6.000000"

    # An unknown historical pack stays unknown even when a live pack exists.
    assert model_lines[1].product_name == "Sugar 1kg"
    assert model_lines[1].base_unit == "kilogram"
    assert model_lines[1].pack_base_quantity is None

    # Missing live labels do not erase a snapshot.
    assert model_lines[2].product_name is None
    assert model_lines[2].base_unit is None
    assert model_lines[2].pack_base_quantity == "3.000000"


def test_line_enrichment_nulls_when_pack_or_canonical_missing() -> None:
    req_id = str(uuid4())
    p_id = str(uuid4())
    line_row = {
        "id": str(uuid4()),
        "purchase_request_id": req_id,
        "workspace_product_id": p_id,
        "quantity": "3.000000",
        "pack_base_quantity": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    # Product without canonical_product or pack_definition
    product_data = {
        "id": p_id,
        "tenant_name": "Raw Product Without Pack",
        "canonical_product": None,
        "pack_definition": [],
    }

    client = FakeEnrichmentClient(
        line_rows=[line_row],
        product_rows=[product_data],
    )
    service = RequestsService()
    lines = service._fetch_lines_for(client, req_id)
    assert len(lines) == 1

    model = _purchase_request_line(lines[0])
    assert model.product_name == "Raw Product Without Pack"
    assert model.base_unit is None
    assert model.pack_base_quantity is None


def test_purchase_request_line_input_rejects_enriched_fields() -> None:
    p_id = uuid4()
    # Valid input
    valid = PurchaseRequestLineInput(
        workspace_product_id=p_id,
        quantity="2",
        note="Test note",
    )
    assert valid.workspace_product_id == p_id

    # Must reject read-only response fields
    with pytest.raises(ValidationError):
        PurchaseRequestLineInput(
            workspace_product_id=p_id,
            quantity="2",
            product_name="Injected Name",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        PurchaseRequestLineInput(
            workspace_product_id=p_id,
            quantity="2",
            base_unit="litre",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        PurchaseRequestLineInput(
            workspace_product_id=p_id,
            quantity="2",
            pack_base_quantity="18",  # type: ignore[call-arg]
        )


def test_insert_lines_snapshots_newest_packs_with_one_batched_lookup() -> None:
    product_ids = [str(uuid4()) for _ in range(3)]
    packs = [
        {
            "id": "00000000-0000-0000-0000-000000000009",
            "workspace_product_id": product_ids[0],
            "created_at": "2026-09-01T00:00:00Z",
            "base_quantity": "18.000000",
        },
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "workspace_product_id": product_ids[0],
            "created_at": "2026-09-15T00:00:00Z",
            "base_quantity": "6.000000",
        },
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "workspace_product_id": product_ids[1],
            "created_at": "2026-09-15T00:00:00Z",
            "base_quantity": "5.000000",
        },
        {
            "id": "00000000-0000-0000-0000-000000000009",
            "workspace_product_id": product_ids[1],
            "created_at": "2026-09-15T00:00:00Z",
            "base_quantity": "25.000000",
        },
    ]
    client = FakeEnrichmentClient(line_rows=[], product_rows=[], pack_rows=packs)
    # Repeated products still share the same lookup and snapshot.
    lines = [
        PurchaseRequestLineInput(workspace_product_id=pid, quantity="2")
        for pid in [*product_ids, product_ids[0]]
    ]
    estimates = [LineEstimate(None, None, None) for _ in lines]
    service = RequestsService()
    rows = service._insert_lines(
        client,
        tenant_id=str(uuid4()),
        request_id=str(uuid4()),
        payload_lines=lines,
        estimates=estimates,
    )
    assert [row["pack_base_quantity"] for row in rows] == [
        "6.000000",
        "25.000000",
        None,
        "6.000000",
    ]
    assert [row["quantity"] for row in rows] == ["2"] * 4
    pack_selects = [
        q for q in client.query_log if q["table"] == "pack_definition" and q["op"] == "select"
    ]
    assert len(pack_selects) == 1
    pack_filter = next(
        q for q in client.query_log if q["table"] == "pack_definition" and q["op"] == "in_"
    )
    assert pack_filter["values"] == product_ids
    assert next(q for q in client.query_log if q["op"] == "insert")["rows"] == rows

    # Replacing/editing lines snapshots the current pack again through the same insert path.
    packs[1]["base_quantity"] = "12.000000"
    replaced = service._insert_lines(
        client,
        tenant_id=str(uuid4()),
        request_id=str(uuid4()),
        payload_lines=lines,
        estimates=estimates,
    )
    assert replaced[0]["pack_base_quantity"] == "12.000000"
    assert rows[0]["pack_base_quantity"] == "6.000000"
