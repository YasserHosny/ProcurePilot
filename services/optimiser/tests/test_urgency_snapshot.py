"""Urgency travels from the stored request snapshot to the solver's request."""

from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_optimiser_worker.repository import _advanced_request_from_snapshot


@pytest.mark.parametrize(
    ("snapshot_extra", "expected"),
    [
        ({"urgency": "urgent"}, "urgent"),
        ({"hard_constraints": {"urgency": "urgent"}}, "urgent"),
        ({"urgency": "normal"}, "normal"),
        ({}, "normal"),
    ],
)
def test_request_keeps_the_urgency_it_was_submitted_with(
    snapshot_extra: dict[str, object], expected: str
) -> None:
    supplier_ids = [str(uuid4()), str(uuid4())]
    row = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "supplier_ids": supplier_ids,
        "items": [{"workspace_product_id": str(uuid4()), "quantity": "1.000000"}],
    }
    snapshot = {
        "rule_version": "advanced-basket-v1",
        "supplier_ids": supplier_ids,
        **snapshot_extra,
    }

    request = _advanced_request_from_snapshot(row=row, snapshot=snapshot)

    assert request.urgency == expected
