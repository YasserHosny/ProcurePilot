from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.requests.schemas import (
    LowStockReport,
    LowStockReportCreate,
    LowStockReportList,
)


def _report(**overrides: object) -> dict:
    base = {
        "id": uuid4(),
        "branch_id": uuid4(),
        "member_id": uuid4(),
        "workspace_product_id": uuid4(),
        "created_at": "2026-09-12T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_low_stock_report_full_shape() -> None:
    report = LowStockReport.model_validate(_report(count_remaining="12.500000"))
    assert report.count_remaining == "12.500000"
    assert report.branch_id is not None
    assert report.member_id is not None
    assert report.workspace_product_id is not None


def test_low_stock_report_minimal_shape() -> None:
    report = LowStockReport.model_validate(_report())
    assert report.count_remaining is None


def test_low_stock_report_create_accepts_valid_payload() -> None:
    payload = LowStockReportCreate(
        branch_id=uuid4(),
        workspace_product_id=uuid4(),
        count_remaining="3.250000",
    )
    assert payload.count_remaining == "3.250000"


def test_low_stock_report_create_rejects_invalid_count_remaining() -> None:
    with pytest.raises(ValidationError):
        LowStockReportCreate(
            branch_id=uuid4(),
            workspace_product_id=uuid4(),
            count_remaining="-1",
        )


def test_low_stock_report_list_with_cursor() -> None:
    lst = LowStockReportList(
        items=[LowStockReport.model_validate(_report())],
        next_cursor="abc",
    )
    assert len(lst.items) == 1
    assert lst.next_cursor == "abc"


def test_low_stock_report_list_without_cursor() -> None:
    lst = LowStockReportList(items=[], next_cursor=None)
    assert lst.items == []
    assert lst.next_cursor is None


def test_low_stock_report_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LowStockReportCreate.model_validate(
            {
                "branch_id": str(uuid4()),
                "workspace_product_id": str(uuid4()),
                "count_remaining": "1.000000",
                "status": "submitted",
            }
        )


# The 201-vs-200 idempotent replay distinction lives in the FastAPI router:
# create_low_stock_report() sets HTTP 200 when the service returns created=False.
