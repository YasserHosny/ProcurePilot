from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.matching import service as matching_service_module
from procurepilot_api.modules.matching.service import MatchingService


class FakeQuery:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self._data = data
        self.filters: list[tuple[str, str, object]] = []
        self.orders: list[tuple[str, bool]] = []
        self.range_args: tuple[int, int] | None = None

    def select(self, _cols: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[object]) -> FakeQuery:
        self.filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: object) -> FakeQuery:
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column: str, value: object) -> FakeQuery:
        self.filters.append(("lte", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self.orders.append((column, desc))
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self.range_args = (start, end)
        return self

    def execute(self) -> object:
        class Result:
            def __init__(self, data: list[dict[str, object]]) -> None:
                self.data = data

        data = list(self._data)
        if self.range_args is not None:
            start, end = self.range_args
            data = data[start : end + 1]
        return Result(data)


class FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, object]]]) -> None:
        self._tables = tables
        self.last_query: FakeQuery | None = None

    def table(self, name: str) -> FakeQuery:
        q = FakeQuery(self._tables.get(name, []))
        self.last_query = q
        if name == "match_task":
            self.match_task_query = q
        return q


def test_list_match_tasks_accepts_query_params_and_enriches_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    task_id = uuid4()
    line_id = uuid4()
    quotation_id = uuid4()
    supplier_id = uuid4()

    fake_task_row = {
        "id": task_id,
        "quotation_line_id": line_id,
        "status": "open",
        "priority": "high",
        "reason": "low_confidence",
        "created_at": now.isoformat(),
        "resolved_at": None,
    }
    fake_line_row = {
        "id": line_id,
        "quotation_id": quotation_id,
        "line_number": 1,
        "original_text": "Organic Whole Milk 2L",
        "quantity": "10",
        "pack_count": 1,
        "unit_size": "2",
        "pack_unit": "litre",
        "unit_price_amount": "2.5000",
        "unit_price_currency": "GBP",
        "vat_rate": "0.2000",
        "delivery_fee_amount": None,
        "delivery_fee_currency": None,
        "discount_amount": None,
        "discount_currency": None,
    }
    fake_quote_row = {
        "id": quotation_id,
        "tenant_id": uuid4(),
        "supplier_id": supplier_id,
        "status": "reviewed",
    }

    client = FakeClient(
        {
            "match_task": [fake_task_row],
            "quotation_line": [
                {
                    "id": line_id,
                    "original_text": "Organic Whole Milk 2L",
                    "line_number": 1,
                    "quotation_id": quotation_id,
                    "quotation": {"id": quotation_id, "supplier_id": supplier_id},
                }
            ],
            "supplier": [{"id": supplier_id, "name": "Fresh Farms Dairy"}],
        }
    )
    monkeypatch.setattr(
        matching_service_module,
        "authenticated_client",
        lambda _settings, _token: client,
    )
    monkeypatch.setattr(
        matching_service_module,
        "_line_row",
        lambda _client, _lid: fake_line_row,
    )
    monkeypatch.setattr(
        matching_service_module,
        "_decision_for_line",
        lambda _client, _lid: None,
    )
    monkeypatch.setattr(
        matching_service_module,
        "_candidate_rows",
        lambda _client, _lid: [],
    )
    monkeypatch.setattr(
        matching_service_module,
        "_quotation_row",
        lambda _client, _qid: fake_quote_row,
    )
    monkeypatch.setattr(
        matching_service_module,
        "_supplier_name",
        lambda _client, _sid: "Fresh Farms Dairy",
    )
    monkeypatch.setattr(
        matching_service_module,
        "_line_rows",
        lambda _client, _qid: [fake_line_row],
    )
    monkeypatch.setattr(
        matching_service_module,
        "_open_task_count",
        lambda _client, _line_ids: 1,
    )

    service = MatchingService()
    result = service.list_match_tasks(
        bearer_token="dummy",
        cursor=None,
        limit=25,
        status="open",
        priority="high",
        reason="low_confidence",
        search="Organic",
        date_from="2026-08-01",
        date_to="2026-08-31",
        sort_by="priority",
        sort_order="asc",
    )

    # Check query filtering and ordering
    assert getattr(client, "match_task_query", None) is not None
    assert ("eq", "status", "open") in client.match_task_query.filters
    assert ("eq", "priority", "high") in client.match_task_query.filters
    assert ("eq", "reason", "low_confidence") in client.match_task_query.filters
    assert ("gte", "created_at", "2026-08-01") in client.match_task_query.filters
    assert ("lte", "created_at", "2026-08-31") in client.match_task_query.filters
    assert ("priority", False) in client.match_task_query.orders  # asc -> desc=False
    assert ("id", False) in client.match_task_query.orders

    # Check item enrichment
    assert len(result.items) == 1
    task = result.items[0]
    assert task.id == task_id
    assert task.supplier_name == "Fresh Farms Dairy"
    assert task.quotation_line.original_text == "Organic Whole Milk 2L"
    assert task.quotation_line.unit_price is not None
    assert task.quotation_line.unit_price.amount == "2.5000"
    assert task.quotation_line.unit_price.currency == "GBP"
    assert task.quotation_line.quoted_line_total is not None
    assert task.quotation_line.quoted_line_total.amount == "30.0000"
    assert task.quotation_line.quoted_line_total.currency == "GBP"
    assert task.quotation.id == quotation_id
    assert task.quotation.line_count == 1
    assert task.quotation.open_match_task_count == 1


def test_match_task_for_line_uses_direct_tenant_scoped_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id = uuid4()
    client = FakeClient({})
    line = {"id": line_id}
    task_row = {"id": uuid4(), "quotation_line_id": line_id}
    expected = object()
    monkeypatch.setattr(
        matching_service_module,
        "authenticated_client",
        lambda _settings, _token: client,
    )
    monkeypatch.setattr(matching_service_module, "_line_row", lambda _client, _id: line)
    monkeypatch.setattr(
        matching_service_module,
        "_latest_task_for_line",
        lambda _client, _id: task_row,
    )
    service = MatchingService()
    monkeypatch.setattr(service, "_task", lambda _client, _row, line_row: expected)

    assert service.match_task_for_line(bearer_token="dummy", line_id=line_id) is expected


def test_matching_pipeline_passes_supplier_code_aliases_to_deterministic_matcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_id = uuid4()
    product_id = uuid4()
    captured_supplier_code_aliases: list[dict[str, object]] = []
    line = {
        "id": line_id,
        "quotation_id": uuid4(),
        "line_number": 1,
        "original_text": "Long supplier wording",
        "extracted_fields": {"supplier_product_code": "SUP-CODE-42"},
    }
    supplier_code_alias = {
        "id": uuid4(),
        "workspace_product_id": product_id,
        "supplier_id": uuid4(),
        "alias_text": "SUP-CODE-42",
    }
    member = type(
        "Member",
        (),
        {"tenant_id": uuid4(), "membership_id": uuid4(), "email": "buyer@example.test"},
    )()
    service = MatchingService()

    monkeypatch.setattr(service, "_backfill_missing_embeddings", lambda _client: None)
    monkeypatch.setattr(matching_service_module, "_decision_for_line", lambda _c, _lid: None)
    monkeypatch.setattr(matching_service_module, "_candidate_rows", lambda _c, _lid: [])
    monkeypatch.setattr(
        matching_service_module,
        "_deterministic_products_for_line",
        lambda _c, _line: [],
    )
    monkeypatch.setattr(matching_service_module, "_aliases_for_line", lambda _c, _line: [])
    monkeypatch.setattr(
        matching_service_module,
        "build_similarity_candidates",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        service,
        "_route_or_accept",
        lambda *_args, **_kwargs: None,
    )

    def fake_find_deterministic_candidate(**kwargs: object) -> None:
        captured_supplier_code_aliases.extend(
            cast(list[dict[str, object]], kwargs["supplier_code_aliases"])
        )
        return None

    monkeypatch.setattr(
        matching_service_module,
        "find_deterministic_candidate",
        fake_find_deterministic_candidate,
    )
    monkeypatch.setattr(
        matching_service_module,
        "_supplier_code_aliases_for_line",
        lambda _client, _line: [supplier_code_alias],
        raising=False,
    )

    service._ensure_pipeline(  # noqa: SLF001
        client=object(),
        member=member,
        quote={"id": line["quotation_id"]},
        lines=[line],
    )

    assert captured_supplier_code_aliases == [supplier_code_alias]


def test_list_match_tasks_search_filters_by_supplier_or_quotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    task1_id, line1_id, q1_id = uuid4(), uuid4(), uuid4()
    task2_id, line2_id, q2_id = uuid4(), uuid4(), uuid4()

    rows = [
        {
            "id": task1_id,
            "quotation_line_id": line1_id,
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": now.isoformat(),
            "resolved_at": None,
        },
        {
            "id": task2_id,
            "quotation_line_id": line2_id,
            "status": "open",
            "priority": "normal",
            "reason": "no_candidate",
            "created_at": now.isoformat(),
            "resolved_at": None,
        },
    ]

    client = FakeClient(
        {
            "match_task": rows,
            "quotation_line": [
                {
                    "id": line1_id,
                    "original_text": "Cheddar Cheese",
                    "line_number": 1,
                    "quotation_id": q1_id,
                    "quotation": {"id": q1_id, "supplier_id": uuid4()},
                },
                {
                    "id": line2_id,
                    "original_text": "Apples",
                    "line_number": 2,
                    "quotation_id": q2_id,
                    "quotation": {"id": q2_id, "supplier_id": uuid4()},
                },
            ],
        }
    )

    orig_table = client.table

    def fake_table(name: str) -> object:
        if name == "supplier":

            class FakeSupplierQuery:
                def select(self, _cols: str) -> object:
                    return self

                def in_(self, col: str, vals: list[object]) -> object:
                    self.vals = vals
                    return self

                def execute(self) -> object:
                    class Res:
                        data = [
                            {"id": v, "name": "Somerset Dairy"} for v in getattr(self, "vals", [])
                        ]

                    return Res()

            return FakeSupplierQuery()
        return orig_table(name)

    client.table = fake_table

    monkeypatch.setattr(
        matching_service_module,
        "authenticated_client",
        lambda _settings, _token: client,
    )

    def fake_line_row(_client: object, lid: UUID) -> dict[str, object]:
        if lid == line1_id:
            return {
                "id": line1_id,
                "quotation_id": q1_id,
                "line_number": 1,
                "original_text": "Cheddar Cheese",
                "quantity": "5",
                "pack_count": None,
                "unit_size": None,
                "pack_unit": None,
                "unit_price_amount": "4.0000",
                "unit_price_currency": "GBP",
                "vat_rate": None,
                "delivery_fee_amount": None,
                "delivery_fee_currency": None,
                "discount_amount": None,
                "discount_currency": None,
            }
        return {
            "id": line2_id,
            "quotation_id": q2_id,
            "line_number": 2,
            "original_text": "Apples",
            "quantity": "20",
            "pack_count": None,
            "unit_size": None,
            "pack_unit": None,
            "unit_price_amount": "1.0000",
            "unit_price_currency": "GBP",
            "vat_rate": None,
            "delivery_fee_amount": None,
            "delivery_fee_currency": None,
            "discount_amount": None,
            "discount_currency": None,
        }

    monkeypatch.setattr(matching_service_module, "_line_row", fake_line_row)
    monkeypatch.setattr(matching_service_module, "_decision_for_line", lambda _c, _lid: None)
    monkeypatch.setattr(matching_service_module, "_candidate_rows", lambda _c, _lid: [])
    monkeypatch.setattr(
        matching_service_module,
        "_quotation_row",
        lambda _c, qid: {
            "id": qid,
            "tenant_id": uuid4(),
            "supplier_id": uuid4(),
            "status": "reviewed",
        },
    )
    monkeypatch.setattr(
        matching_service_module,
        "_supplier_name",
        lambda _c, sid: "Somerset Dairy" if sid else "",
    )

    service = MatchingService()
    # Search matches item 1 ("cheddar")
    res1 = service.list_match_tasks(bearer_token="dummy", search="cheddar")
    assert len(res1.items) == 1
    assert res1.items[0].id == task1_id

    # Search matches supplier ("somerset")
    res2 = service.list_match_tasks(bearer_token="dummy", search="somerset")
    assert len(res2.items) == 2  # both share mock supplier name

    # Search non-matching
    res3 = service.list_match_tasks(bearer_token="dummy", search="nonexistent")
    assert len(res3.items) == 0


def test_list_match_tasks_search_finds_matches_beyond_first_page_before_paginating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    first_task_id, first_line_id, first_qid = uuid4(), uuid4(), uuid4()
    middle_task_id, middle_line_id, middle_qid = uuid4(), uuid4(), uuid4()
    second_task_id, second_line_id, second_qid = uuid4(), uuid4(), uuid4()

    rows = [
        {
            "id": first_task_id,
            "quotation_line_id": first_line_id,
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": now.isoformat(),
            "resolved_at": None,
        },
        {
            "id": second_task_id,
            "quotation_line_id": second_line_id,
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": now.isoformat(),
            "resolved_at": None,
        },
    ]
    rows.insert(
        1,
        {
            "id": middle_task_id,
            "quotation_line_id": middle_line_id,
            "status": "open",
            "priority": "normal",
            "reason": "low_confidence",
            "created_at": now.isoformat(),
            "resolved_at": None,
        },
    )

    client = FakeClient(
        {
            "match_task": rows,
            "quotation_line": [
                {
                    "id": first_line_id,
                    "original_text": "Other Product",
                    "line_number": 1,
                    "quotation_id": first_qid,
                    "quotation": {"id": first_qid, "supplier_id": None},
                },
                {
                    "id": middle_line_id,
                    "original_text": "Other Product",
                    "line_number": 1,
                    "quotation_id": middle_qid,
                    "quotation": {"id": middle_qid, "supplier_id": None},
                },
                {
                    "id": second_line_id,
                    "original_text": "Needle Product",
                    "line_number": 2,
                    "quotation_id": second_qid,
                    "quotation": {"id": second_qid, "supplier_id": None},
                },
            ],
        }
    )
    monkeypatch.setattr(
        matching_service_module,
        "authenticated_client",
        lambda _settings, _token: client,
    )

    def fake_line_row(_client: object, lid: UUID) -> dict[str, object]:
        text = "Needle Product" if lid == second_line_id else "Other Product"
        qid = {
            first_line_id: first_qid,
            middle_line_id: middle_qid,
            second_line_id: second_qid,
        }[lid]
        return {
            "id": lid,
            "quotation_id": qid,
            "line_number": 2 if lid == second_line_id else 1,
            "original_text": text,
            "quantity": "1",
            "pack_count": None,
            "unit_size": None,
            "pack_unit": None,
            "unit_price_amount": "1.0000",
            "unit_price_currency": "GBP",
            "vat_rate": None,
            "delivery_fee_amount": None,
            "delivery_fee_currency": None,
            "discount_amount": None,
            "discount_currency": None,
        }

    monkeypatch.setattr(matching_service_module, "_line_row", fake_line_row)
    monkeypatch.setattr(matching_service_module, "_decision_for_line", lambda _c, _lid: None)
    monkeypatch.setattr(matching_service_module, "_candidate_rows", lambda _c, _lid: [])
    monkeypatch.setattr(
        matching_service_module,
        "_quotation_row",
        lambda _c, qid: {
            "id": qid,
            "tenant_id": uuid4(),
            "supplier_id": None,
            "status": "reviewed",
        },
    )

    service = MatchingService()
    task_calls = 0
    original_task = service._task

    def spied_task(
        c: object, r: dict[str, object], line_row: dict[str, object] | None = None
    ) -> object:
        nonlocal task_calls
        task_calls += 1
        return original_task(c, r, line_row=line_row)

    monkeypatch.setattr(service, "_task", spied_task)

    result = service.list_match_tasks(
        bearer_token="dummy",
        limit=1,
        search="needle",
    )

    assert [task.id for task in result.items] == [second_task_id]
    assert task_calls == 1
    assert result.next_cursor is None
