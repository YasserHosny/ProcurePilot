from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from procurepilot_api.modules.quotations.review_gate import blocking_low_confidence_fields


class Query:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __getattr__(self, _name: str) -> Callable[..., Query]:
        return lambda *_args, **_kwargs: self

    def execute(self) -> QueryResult:
        return QueryResult(self.rows)


@dataclass
class QueryResult:
    data: list[dict[str, object]]


class Client:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> Query:
        return Query(self.rows)


def test_gate_ignores_currency_hint_and_supplier_name_after_supplier_selection() -> None:
    rows = [
        {
            "id": str(uuid4()),
            "entity_type": "quotation",
            "entity_id": str(uuid4()),
            "field_name": name,
        }
        for name in ("suggested_currency", "supplier_name", "unit_price")
    ]
    result = blocking_low_confidence_fields(Client(rows), uuid4(), 0.85, supplier_id=uuid4())
    assert [item["field_name"] for item in result] == ["unit_price"]


def test_gate_keeps_supplier_name_blocking_without_supplier_selection() -> None:
    row = {
        "id": str(uuid4()),
        "entity_type": "quotation",
        "entity_id": str(uuid4()),
        "field_name": "supplier_name",
    }
    result = blocking_low_confidence_fields(Client([row]), uuid4(), 0.85, supplier_id=None)
    assert result == [row]
