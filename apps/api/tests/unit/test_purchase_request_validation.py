from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from procurepilot_api.errors import (
    UnprocessableEntityError,
    _format_loc,
    _validation_details,
)
from procurepilot_api.modules.requests.schemas import PurchaseRequestLineInput
from procurepilot_api.modules.requests.service import RequestsService


def test_format_loc_helper() -> None:
    assert _format_loc(["body", "lines", 1, "quantity"]) == "lines[1].quantity"
    assert _format_loc(["body", "required_by_date"]) == "required_by_date"
    assert _format_loc(["body", "items", 0, "name"]) == "items[0].name"
    assert _format_loc(["query", "limit"]) == "limit"
    assert _format_loc([]) == ""


def test_generic_validation_handler_details_shape() -> None:
    raw_errors = [
        {
            "loc": ("body", "lines", 1, "quantity"),
            "msg": "Input should be greater than 0",
            "type": "greater_than",
            "input": "0",  # sensitive or raw input value
        },
        {
            "loc": ("body", "required_by_date"),
            "msg": "Date is invalid",
            "type": "date_from_datetime_parsing",
            "input": "invalid-date",
        },
    ]
    details = _validation_details(raw_errors)
    assert len(details) == 2

    first = details[0]
    assert first["loc"] == ["body", "lines", 1, "quantity"]
    assert first["type"] == "greater_than"
    assert first["field"] == "lines[1].quantity"
    assert first["reason"] == "greater_than"
    assert "input" not in first  # must not echo raw input values

    second = details[1]
    assert second["loc"] == ["body", "required_by_date"]
    assert second["type"] == "date_from_datetime_parsing"
    assert second["field"] == "required_by_date"
    assert second["reason"] == "date_from_datetime_parsing"
    assert "input" not in second


def test_validate_quantity_rejects_zero_and_negative() -> None:
    service = RequestsService()
    pid = uuid4()
    line_zero = PurchaseRequestLineInput(workspace_product_id=pid, quantity="0")
    with pytest.raises(UnprocessableEntityError) as exc_info:
        service._validate_request_lines([line_zero])
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[0].quantity",
        "reason": "quantity_not_positive",
    }

    line_zero_decimal = PurchaseRequestLineInput(workspace_product_id=pid, quantity="0.000000")
    with pytest.raises(UnprocessableEntityError) as exc_info2:
        service._validate_request_lines([line_zero_decimal])
    assert exc_info2.value.details == {
        "field": "lines[0].quantity",
        "reason": "quantity_not_positive",
    }


def test_validate_quantity_accepts_positive() -> None:
    service = RequestsService()
    pid = uuid4()
    line = PurchaseRequestLineInput(workspace_product_id=pid, quantity="5.123456")
    # Should not raise
    service._validate_request_lines([line])


def test_validate_rejects_duplicate_workspace_product_id() -> None:
    service = RequestsService()
    pid = uuid4()
    line1 = PurchaseRequestLineInput(workspace_product_id=pid, quantity="1")
    line2 = PurchaseRequestLineInput(workspace_product_id=pid, quantity="2")
    with pytest.raises(UnprocessableEntityError) as exc_info:
        service._validate_request_lines([line1, line2])
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[1].workspace_product_id",
        "reason": "duplicate_product",
    }


def test_validate_required_by_date_on_create() -> None:
    service = RequestsService()
    past_date = datetime.now(UTC).date() - timedelta(days=2)
    with pytest.raises(UnprocessableEntityError) as exc_info:
        service._validate_required_by_date(past_date)
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "required_by_date",
        "reason": "required_by_in_the_past",
    }

    today = datetime.now(UTC).date()
    service._validate_required_by_date(today)
    service._validate_required_by_date(today + timedelta(days=5))


def test_validate_products_exist_rejects_missing() -> None:
    service = RequestsService()
    pid1 = uuid4()
    pid2 = uuid4()
    # Mock client where pid1 exists but pid2 does not
    client = SimpleNamespace(
        table=lambda t: SimpleNamespace(
            select=lambda cols: SimpleNamespace(
                in_=lambda col, vals: SimpleNamespace(
                    execute=lambda: SimpleNamespace(data=[{"id": str(pid1)}])
                )
            )
        )
    )
    lines = [
        PurchaseRequestLineInput(workspace_product_id=pid1, quantity="1"),
        PurchaseRequestLineInput(workspace_product_id=pid2, quantity="2"),
    ]
    with pytest.raises(UnprocessableEntityError) as exc_info:
        service._validate_products_exist(client, lines=lines)
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "lines[1].workspace_product_id",
        "reason": "product_not_found",
    }


def test_validate_cost_centre_branch_mismatch() -> None:
    service = RequestsService()
    cc_id = uuid4()
    branch_a = uuid4()
    branch_b = uuid4()

    # Cost centre exists with branch_b
    client = SimpleNamespace(
        table=lambda t: SimpleNamespace(
            select=lambda cols: SimpleNamespace(
                eq=lambda col, val: SimpleNamespace(
                    execute=lambda: SimpleNamespace(
                        data=[{"id": str(cc_id), "branch_id": str(branch_b)}]
                    )
                )
            )
        )
    )

    with pytest.raises(UnprocessableEntityError) as exc_info:
        service._validate_cost_centre_branch(client, cost_centre_id=cc_id, branch_id=branch_a)
    assert exc_info.value.status_code == 422
    assert exc_info.value.details == {
        "field": "cost_centre_id",
        "reason": "cost_centre_branch_mismatch",
    }

    # Matches branch_b -> succeeds
    service._validate_cost_centre_branch(client, cost_centre_id=cc_id, branch_id=branch_b)

    # Cost centre has null branch_id -> succeeds for any branch
    client_null_branch = SimpleNamespace(
        table=lambda t: SimpleNamespace(
            select=lambda cols: SimpleNamespace(
                eq=lambda col, val: SimpleNamespace(
                    execute=lambda: SimpleNamespace(data=[{"id": str(cc_id), "branch_id": None}])
                )
            )
        )
    )
    service._validate_cost_centre_branch(
        client_null_branch, cost_centre_id=cc_id, branch_id=branch_a
    )


def test_validate_cost_centre_not_found() -> None:
    service = RequestsService()
    cc_id = uuid4()
    branch_a = uuid4()

    # Cost centre not found in tenant
    client_empty = SimpleNamespace(
        table=lambda t: SimpleNamespace(
            select=lambda cols: SimpleNamespace(
                eq=lambda col, val: SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))
            )
        )
    )
    with pytest.raises(UnprocessableEntityError) as exc_empty:
        service._validate_cost_centre_branch(client_empty, cost_centre_id=cc_id, branch_id=branch_a)
    assert exc_empty.value.status_code == 422
    assert exc_empty.value.details == {
        "field": "cost_centre_id",
        "reason": "cost_centre_not_found",
    }
