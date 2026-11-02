from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.offers import price_history
from procurepilot_api.modules.savings import baseline
from procurepilot_api.modules.savings.baseline import capture_baseline
from procurepilot_api.modules.savings.schemas import Money


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self._rows: list[dict[str, object]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> None:
        if "purchase_order_line" in sql:
            self._connection.po_params = params
            self._rows = self._connection.po_rows
        else:
            self._rows = self._connection.rows

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


class _Connection:
    """Serves landed-cost rows for the quote query and PO rows for the PO query.

    PO rows are filtered the way LAST_PO_PRICE_SQL filters them (status, excluded order, base
    unit, then limit 1) so the tests exercise the same contract the SQL implements; order is
    the caller's.
    """

    def __init__(
        self,
        rows: list[dict[str, object]],
        po_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = rows
        self._all_po_rows = po_rows or []
        self.po_params: dict[str, object] | None = None

    @property
    def po_rows(self) -> list[dict[str, object]]:
        params = self.po_params or {}
        statuses = params.get("statuses", [])
        excluded = params.get("exclude_order_id")
        base_unit = params.get("base_unit")
        return [
            row
            for row in self._all_po_rows
            if row["status"] in statuses
            and row["purchase_order_id"] != excluded
            and (base_unit is None or row["base_unit"] == base_unit)
        ][:1]

    def cursor(self, **_kwargs: object) -> _Cursor:
        return _Cursor(self)


def _quote_row(
    product_id: object,
    amount: str,
    quantity: str = "10.000000",
    *,
    packs: str | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "landed_cost_id": uuid4(),
        "workspace_product_id": product_id,
        "supplier_id": uuid4(),
        "supplier_name": "Supplier",
        "recorded_at": now,
        "valid_from": now,
        "valid_to": None,
        "total_amount": Decimal(amount),
        "total_currency": "EGP",
        "normalised_base_quantity": Decimal(quantity),
        "quantity": Decimal(quantity if packs is None else packs),
        "base_unit": "each",
    }


def test_quoted_pack_price_baseline_has_no_rounding_noise() -> None:
    product_id = uuid4()
    row = _quote_row(product_id, "1275.0000", "675.000000", packs="15.000000")
    row.update(total_currency="SAR", base_unit="kilogram")
    capture = capture_baseline(
        _Connection([row]),
        product_id=product_id,
        quantity=Decimal("675.000000"),
        actual=Money(amount=Decimal("1230.0000"), currency="SAR"),
        base_unit="kilogram",
    )

    assert capture.policy == "last_paid"
    assert capture.value == Money(amount=Decimal("1275.0000"), currency="SAR")
    assert capture.delta == Money(amount=Decimal("45.0000"), currency="SAR")
    assert capture.unit_price == Money(amount=Decimal("1.8889"), currency="SAR")
    assert capture.calculation_inputs["landed_total"] == {
        "amount": "1275.0000",
        "currency": "SAR",
    }
    assert capture.calculation_inputs["landed_quantity"] == "15.000000"
    assert capture.calculation_inputs["landed_base_quantity"] == "675.000000"


def test_quoted_partial_pack_baseline_rounds_only_the_final_value() -> None:
    product_id = uuid4()
    row = _quote_row(product_id, "1275.0000", "675.000000", packs="15.000000")
    row.update(total_currency="SAR", base_unit="kilogram")
    capture = capture_baseline(
        _Connection([row]),
        product_id=product_id,
        quantity=Decimal("30.000000"),
        actual=Money(amount=Decimal("50.0000"), currency="SAR"),
        base_unit="kilogram",
    )

    assert capture.policy == "last_paid"
    assert capture.value == Money(amount=Decimal("56.6667"), currency="SAR")
    assert capture.delta == Money(amount=Decimal("6.6667"), currency="SAR")
    assert capture.unit_price == Money(amount=Decimal("1.8889"), currency="SAR")


def test_quoted_average_baseline_has_no_rounding_noise() -> None:
    product_id = uuid4()
    rows = [
        _quote_row(product_id, "85.0000", "45.000000", packs="1.000000"),
        _quote_row(product_id, "85.0000", "45.000000", packs="1.000000"),
    ]
    for row in rows:
        row.update(total_currency="SAR", base_unit="kilogram")

    value = baseline._quoted_baseline_value(rows, Decimal("675.000000"), average=True)

    assert Money(amount=value, currency="SAR") == Money(amount=Decimal("1275.0000"), currency="SAR")


def _po_row(
    *,
    unit_price: str,
    status: str = "received",
    pack: str | None = None,
    order_id: UUID | None = None,
    currency: str = "EGP",
    base_unit: str = "each",
) -> dict[str, object]:
    return {
        "purchase_order_line_id": uuid4(),
        "purchase_order_id": order_id or uuid4(),
        "order_number": "PO-1",
        "order_date": date(2026, 10, 1),
        "status": status,
        "base_unit": base_unit,
        "unit_price_amount": Decimal(unit_price),
        "unit_price_currency": currency,
        "pack_base_quantity": None if pack is None else Decimal(pack),
    }


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


def test_last_po_price_wins_over_quotes() -> None:
    product_id = uuid4()
    po = _po_row(unit_price="9.0000")
    capture = capture_baseline(
        _Connection([_quote_row(product_id, "50.0000")], [po]),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.policy == "last_po_price"
    assert capture.source_po_line_ids == [po["purchase_order_line_id"]]
    assert capture.source_landed_cost_ids == []
    assert capture.value == Money(amount=Decimal("90.0000"), currency="EGP")
    assert capture.delta == Money(amount=Decimal("10.0000"), currency="EGP")
    assert capture.calculation_inputs["selected_metric"] == "last_po_price"
    assert capture.calculation_inputs["source_po_line_ids"] == [str(po["purchase_order_line_id"])]


def test_draft_and_cancelled_orders_are_not_a_baseline() -> None:
    product_id = uuid4()
    capture = capture_baseline(
        _Connection(
            [_quote_row(product_id, "50.0000")],
            [
                _po_row(unit_price="1.0000", status="draft"),
                _po_row(unit_price="1.0000", status="cancelled"),
            ],
        ),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("45.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.policy == "last_paid"
    assert capture.value == Money(amount=Decimal("50.0000"), currency="EGP")
    assert capture.source_po_line_ids is None


def test_the_outcomes_own_purchase_order_is_excluded() -> None:
    product_id = uuid4()
    own_order = uuid4()
    own = _po_row(unit_price="8.0000", order_id=own_order)
    previous = _po_row(unit_price="9.5000")
    connection = _Connection([], [own, previous])
    capture = capture_baseline(
        connection,
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="EGP"),
        base_unit="each",
        exclude_purchase_order_id=own_order,
    )

    assert connection.po_params is not None
    assert connection.po_params["exclude_order_id"] == own_order
    assert capture.source_po_line_ids == [previous["purchase_order_line_id"]]
    assert capture.value == Money(amount=Decimal("95.0000"), currency="EGP")
    assert capture.calculation_inputs["excluded_purchase_order_id"] == str(own_order)


def test_pack_price_is_normalised_to_the_outcomes_base_units() -> None:
    """Egg carton of 30 at 172 per carton vs an outcome of 60 pieces for 330."""
    product_id = uuid4()
    capture = capture_baseline(
        _Connection([], [_po_row(unit_price="172.0000", pack="30.000000")]),
        product_id=product_id,
        quantity=Decimal("60.000000"),
        actual=Money(amount=Decimal("330.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.policy == "last_po_price"
    # 60 pieces = 2 cartons x 172; not 60 x 5.7333 (rounded per-piece price) = 343.998.
    assert capture.value == Money(amount=Decimal("344.0000"), currency="EGP")
    assert capture.delta == Money(amount=Decimal("14.0000"), currency="EGP")
    assert capture.unit_price == Money(amount=Decimal("5.7333"), currency="EGP")
    assert capture.calculation_inputs["pack_base_quantity"] == "30.000000"


def test_po_line_in_another_base_unit_is_skipped() -> None:
    product_id = uuid4()
    capture = capture_baseline(
        _Connection(
            [],
            [_po_row(unit_price="1.0000", base_unit="kilogram"), _po_row(unit_price="9.0000")],
        ),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.value == Money(amount=Decimal("90.0000"), currency="EGP")


def test_po_currency_mismatch_is_none_available() -> None:
    product_id = uuid4()
    capture = capture_baseline(
        _Connection(
            [_quote_row(product_id, "50.0000")], [_po_row(unit_price="9.0000", currency="USD")]
        ),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("80.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.policy == "none_available"
    assert capture.value is None
    assert capture.delta is None
    assert capture.calculation_inputs["reason"] == "currency_mismatch"


def test_without_purchase_orders_the_quote_fallback_is_unchanged() -> None:
    product_id = uuid4()
    capture = capture_baseline(
        _Connection([_quote_row(product_id, "50.0000")], []),
        product_id=product_id,
        quantity=Decimal("10.000000"),
        actual=Money(amount=Decimal("45.0000"), currency="EGP"),
        base_unit="each",
    )

    assert capture.policy == "last_paid"
    assert capture.delta == Money(amount=Decimal("5.0000"), currency="EGP")


def test_inclusive_landed_baseline_compares_net_to_net() -> None:
    product = uuid4()
    row = _quote_row(product, "4830.0000", "350", packs="350")
    row.update(vat_amount=Decimal("630.0000"), total_currency="SAR", rule_version="landed-cost-v2")
    capture = capture_baseline(
        _Connection([row]),
        product_id=product,
        quantity=Decimal("350"),
        actual=Money(amount=Decimal("4200"), currency="SAR"),
    )
    assert capture.value == Money(amount=Decimal("4200.0000"), currency="SAR")
    assert capture.delta == Money(amount=Decimal("0.0000"), currency="SAR")
    assert capture.calculation_inputs["landed_vat"] == {"amount": "630.0000", "currency": "SAR"}
    assert baseline.CALCULATION_VERSION == "saving-baseline-v4"


def test_rolling_quoted_baseline_uses_net_values() -> None:
    row = _quote_row(uuid4(), "4830.0000", "350")
    row["vat_amount"] = Decimal("630.0000")
    assert baseline._quoted_baseline_value([row, row], Decimal("350"), average=True) == Decimal(
        "4200.0000"
    )
    assert baseline._history_point(row).normalised_unit_price.amount == "12.0000"


def test_po_baseline_uses_net_unit_price_excluding_line_tax() -> None:
    po = _po_row(unit_price="12.0000", currency="SAR")
    po.update(tax_amount=Decimal("180"), tax_currency="SAR")
    capture = capture_baseline(
        _Connection([], [po]),
        product_id=uuid4(),
        quantity=Decimal("100"),
        actual=Money(amount=Decimal("1200"), currency="SAR"),
    )
    assert capture.value == Money(amount=Decimal("1200.0000"), currency="SAR")
    assert capture.delta.amount == Decimal("0.0000")
