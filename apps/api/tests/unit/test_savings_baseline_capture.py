from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from procurepilot_api.modules.offers import price_history
from procurepilot_api.modules.savings.baseline import capture_baseline
from procurepilot_api.modules.savings.schemas import Money


class _Cursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object) -> None:
        return None

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def cursor(self, **_kwargs: object) -> _Cursor:
        return _Cursor(self._rows)


def test_capture_baseline_reuses_offer_price_history_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"normalised": 0, "summary": 0}

    def normalised(total_amount: object, base_quantity: object) -> Decimal:
        called["normalised"] += 1
        return price_history.normalised_unit_price(total_amount, base_quantity)

    def summary(points: object, *, window_start: object) -> object:
        called["summary"] += 1
        return price_history.price_history_summary(points, window_start=window_start)

    monkeypatch.setattr(
        "procurepilot_api.modules.savings.baseline.normalised_unit_price",
        normalised,
    )
    monkeypatch.setattr("procurepilot_api.modules.savings.baseline.price_history_summary", summary)
    landed_cost_id = uuid4()
    supplier_id = uuid4()
    product_id = uuid4()
    capture = capture_baseline(
        _Connection(
            [
                {
                    "landed_cost_id": landed_cost_id,
                    "workspace_product_id": product_id,
                    "supplier_id": supplier_id,
                    "supplier_name": "Supplier",
                    "recorded_at": __import__("datetime").datetime.now(__import__("datetime").UTC),
                    "valid_from": __import__("datetime").datetime.now(__import__("datetime").UTC),
                    "valid_to": None,
                    "total_amount": Decimal("90.0000"),
                    "total_currency": "GBP",
                    "normalised_base_quantity": Decimal("10.000000"),
                    "quantity": Decimal("10.000000"),
                    "base_unit": "each",
                }
            ]
        ),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="GBP"),
    )

    assert called == {"normalised": 1, "summary": 1}
    assert capture.policy == "last_paid"
    assert capture.value == Money(amount=Decimal("90.0000"), currency="GBP")
    assert capture.delta == Money(amount=Decimal("10.0000"), currency="GBP")


def test_capture_baseline_records_none_available_without_hiding_actual() -> None:
    capture = capture_baseline(
        _Connection([]),
        product_id=uuid4(),
        quantity=Decimal("1.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="GBP"),
    )

    assert capture.policy == "none_available"
    assert capture.value is None
    assert capture.delta is None
    assert capture.calculation_inputs["actual_value"] == {"amount": "80.0000", "currency": "GBP"}
