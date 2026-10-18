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


class RecordingSelectQuery:
    def __init__(
        self, table_name: str, rows: list[dict[str, object]], tracker: list[dict[str, object]]
    ) -> None:
        self.table_name = table_name
        self.rows = rows
        self.tracker = tracker
        self.filters: list[tuple[str, str]] = []
        self.in_filters: list[tuple[str, list[str]]] = []

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

    def order(self, *_args: object, **_kwargs: object) -> RecordingSelectQuery:
        return self

    def execute(self) -> SimpleNamespace:
        data = self.rows
        for col, val in self.filters:
            data = [r for r in data if str(r.get(col)) == val]
        for col, vals in self.in_filters:
            allowed = set(vals)
            data = [r for r in data if str(r.get(col)) in allowed]
        return SimpleNamespace(data=data)


class FakeEnrichmentClient:
    def __init__(
        self,
        *,
        line_rows: list[dict[str, object]],
        product_rows: list[dict[str, object]],
    ) -> None:
        self.line_rows = line_rows
        self.product_rows = product_rows
        self.query_log: list[dict[str, object]] = []

    def table(self, name: str) -> RecordingSelectQuery:
        if name == "purchase_request_line":
            return RecordingSelectQuery(name, self.line_rows, self.query_log)
        if name == "workspace_product":
            return RecordingSelectQuery(name, self.product_rows, self.query_log)
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
        "quantity_received": None,
        "note": "Missing product line",
        "estimated_unit_price_amount": None,
        "estimated_unit_price_currency": None,
        "estimated_unit_price_source_landed_cost_id": None,
        "estimated_at": None,
        "created_at": datetime.now(UTC).isoformat(),
    }

    # product 1 has multiple pack definitions; newest created_at must win
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

    # product 2 has a tie in created_at; id desc tie-breaker must win
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

    # Line 1: picked newest pack (18.000000)
    assert model_lines[0].product_name == "Full Cream Milk"
    assert model_lines[0].base_unit == "litre"
    assert model_lines[0].pack_base_quantity == "18.000000"

    # Line 2: picked tie-breaker high ID (25.000000)
    assert model_lines[1].product_name == "Sugar 1kg"
    assert model_lines[1].base_unit == "kilogram"
    assert model_lines[1].pack_base_quantity == "25.000000"

    # Line missing: nulls when product not found
    assert model_lines[2].product_name is None
    assert model_lines[2].base_unit is None
    assert model_lines[2].pack_base_quantity is None


def test_line_enrichment_nulls_when_pack_or_canonical_missing() -> None:
    req_id = str(uuid4())
    p_id = str(uuid4())
    line_row = {
        "id": str(uuid4()),
        "purchase_request_id": req_id,
        "workspace_product_id": p_id,
        "quantity": "3.000000",
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
