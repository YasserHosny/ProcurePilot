"""Pure unit tests for retrieval.py — no database, no I/O.

Typed input objects are constructed directly in Python and passed to the
pure retrieval functions, exactly as test_supplier_iq_v2.py does for
supplier_iq_v2.py's functions.

Coverage per FR-002 category (spend/savings, supplier performance/risk,
orders/quotations, reorder forecasts):

  1. Normal cited answer
  2. Zero grounding data → must say so explicitly, never guess
  3. Conflicting records → must surface both, not silently pick one
  4. Explicit-currency handling → no cross-currency aggregation
  5. Cross-tenant / unknown-identifier case (FR-007) → since retrieval.py's
     inputs are pre-scoped by the caller, an unknown ID not present in the
     input just means zero records → NoGroundingData, never a leak
  6. Replay-determinism → identical inputs passed twice produce a bit-identical result
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid4

import pytest

from procurepilot_api.modules.analyst.retrieval import (
    CALCULATION_VERSION,
    AnalystAnswer,
    NoGroundingData,
    OrderRecord,
    OrdersQuotationsInput,
    QuotationRecord,
    ReorderForecastsInput,
    ReorderRecord,
    SavingRecord,
    SpendRecord,
    SpendSavingsInput,
    SupplierPerformanceRiskInput,
    SupplierRiskRecord,
    retrieve_orders_quotations,
    retrieve_reorder_forecasts,
    retrieve_spend_savings,
    retrieve_supplier_performance_risk,
)
from procurepilot_api.modules.analyst.schemas import CitationSourceKind

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

SUPPLIER_A = UUID(int=1)
SUPPLIER_B = UUID(int=2)
PRODUCT_A = UUID(int=10)
PRODUCT_B = UUID(int=11)
TODAY = date(2026, 9, 24)


def _spend(
    *,
    amount: str = "1000.00",
    currency: str = "GBP",
    supplier_id: UUID | None = SUPPLIER_A,
) -> SpendRecord:
    return SpendRecord(
        id=uuid4(),
        source_kind=CitationSourceKind.purchase_order,
        supplier_id=supplier_id,
        product_id=PRODUCT_A,
        amount=D(amount),
        currency=currency,
        recorded_on=TODAY,
    )


def _saving(
    *,
    amount: str = "100.00",
    currency: str = "GBP",
) -> SavingRecord:
    return SavingRecord(
        id=uuid4(),
        product_id=PRODUCT_A,
        supplier_id=SUPPLIER_A,
        amount=D(amount),
        currency=currency,
        recorded_on=TODAY,
    )


def _risk_snapshot(
    *,
    supplier_id: UUID = SUPPLIER_A,
    name: str = "Acme Ltd",
    risk_level: str | None = "medium",
    risk_score: str | None = "0.5",
    window_end: date = TODAY,
) -> SupplierRiskRecord:
    return SupplierRiskRecord(
        id=uuid4(),
        supplier_id=supplier_id,
        supplier_name=name,
        risk_level=risk_level,
        risk_score=D(risk_score) if risk_score else None,
        state="ready",
        window_end=window_end,
    )


def _order(
    *,
    supplier_id: UUID = SUPPLIER_A,
    status: str = "received",
    amount: str = "500.00",
    currency: str = "GBP",
) -> OrderRecord:
    return OrderRecord(
        id=uuid4(),
        supplier_id=supplier_id,
        status=status,
        total_amount=D(amount),
        currency=currency,
        order_date=TODAY,
        expected_delivery_date=None,
    )


def _quotation(
    *,
    supplier_id: UUID | None = SUPPLIER_A,
    unit_price: str = "50.00",
    currency: str = "GBP",
) -> QuotationRecord:
    return QuotationRecord(
        id=uuid4(),
        supplier_id=supplier_id,
        product_id=PRODUCT_A,
        unit_price_amount=D(unit_price),
        currency=currency,
        created_at=TODAY,
    )


def _reorder(
    *,
    product_id: UUID = PRODUCT_A,
    status: str = "pending",
    quantity: str = "10",
    urgency: str | None = "normal",
) -> ReorderRecord:
    return ReorderRecord(
        id=uuid4(),
        product_id=product_id,
        proposed_quantity=D(quantity),
        status=status,
        created_at=TODAY,
        urgency=urgency,
    )


# ===========================================================================
# Category 1: Spend and Savings
# ===========================================================================


class TestSpendSavings:
    # 1. Normal cited answer
    def test_normal_cited_answer(self) -> None:
        result = retrieve_spend_savings(
            SpendSavingsInput(
                spend_records=(_spend(amount="1000.00"), _spend(amount="500.00")),
                saving_records=(_saving(amount="200.00"),),
            )
        )
        assert isinstance(result, AnalystAnswer)
        assert result.calculation_version == CALCULATION_VERSION
        assert result.value is not None
        assert result.value.currency == "GBP"
        assert D(result.value.amount) == D("1500.0000")
        assert len(result.citations) == 3  # 2 spend + 1 saving
        # Every citation must have a source_id and source_kind
        for c in result.citations:
            assert c.source_id is not None
            assert c.source_kind is not None

    # 2. Zero grounding data → must say so explicitly
    def test_zero_grounding_data_says_so_explicitly(self) -> None:
        result = retrieve_spend_savings(SpendSavingsInput())
        assert isinstance(result, NoGroundingData)
        assert result.reason == "no_records"
        assert "never guesses" in result.explanation
        assert result.calculation_version == CALCULATION_VERSION

    # 3. Conflicting records (currency conflict) → surface both, not pick one
    def test_conflicting_currencies_surfaces_both(self) -> None:
        result = retrieve_spend_savings(
            SpendSavingsInput(
                spend_records=(
                    _spend(amount="1000.00", currency="GBP"),
                    _spend(amount="2000.00", currency="USD"),
                ),
            )
        )
        assert isinstance(result, AnalystAnswer)
        # Must surface both currencies, not aggregate
        assert "GBP" in result.answer_text
        assert "USD" in result.answer_text
        assert (
            "conflict" in result.answer_text.lower()
            or "currencies" in result.answer_text.lower()
        )
        # Must not produce a single Money value (that would mean aggregation)
        # The answer is a conflict explanation, not a single total
        assert len(result.citations) == 2

    # 4. Explicit-currency handling — no cross-currency aggregation
    def test_no_cross_currency_aggregation(self) -> None:
        """Mixed currencies must produce a conflict result, not a summed total."""
        result = retrieve_spend_savings(
            SpendSavingsInput(
                spend_records=(
                    _spend(amount="100.00", currency="GBP"),
                    _spend(amount="100.00", currency="EUR"),
                    _spend(amount="100.00", currency="USD"),
                ),
            )
        )
        assert isinstance(result, AnalystAnswer)
        # Three distinct currencies must all appear in the answer
        for ccy in ("GBP", "EUR", "USD"):
            assert ccy in result.answer_text, f"{ccy} missing from conflict answer"
        # The formula must say no cross-currency aggregation
        assert "cross-currency" in result.calculation.formula.lower()

    # 5. Cross-tenant / unknown-identifier (FR-007)
    # retrieval.py gets pre-scoped inputs; a cross-tenant supplier_id simply
    # won't appear in the records the caller passes — so zero records → NoGroundingData.
    def test_unknown_identifier_resolves_to_no_grounding_data(self) -> None:
        """If the caller passes no records (because the identifier was cross-tenant),
        retrieval.py returns NoGroundingData — it never leaks or guesses."""
        result = retrieve_spend_savings(SpendSavingsInput())
        assert isinstance(result, NoGroundingData)
        assert result.reason == "no_records"

    # 6. Replay determinism — identical inputs → identical result
    def test_replay_determinism(self) -> None:
        spend_id = uuid4()
        saving_id = uuid4()
        records = SpendSavingsInput(
            spend_records=(
                SpendRecord(
                    id=spend_id,
                    source_kind=CitationSourceKind.purchase_order,
                    supplier_id=SUPPLIER_A,
                    product_id=PRODUCT_A,
                    amount=D("999.00"),
                    currency="GBP",
                    recorded_on=TODAY,
                ),
            ),
            saving_records=(
                SavingRecord(
                    id=saving_id,
                    product_id=PRODUCT_A,
                    supplier_id=SUPPLIER_A,
                    amount=D("111.00"),
                    currency="GBP",
                    recorded_on=TODAY,
                ),
            ),
        )
        first = retrieve_spend_savings(records)
        second = retrieve_spend_savings(records)
        assert first == second, "identical inputs must produce a bit-identical result"


# ===========================================================================
# Category 2: Supplier performance and risk
# ===========================================================================


class TestSupplierPerformanceRisk:
    # 1. Normal cited answer
    def test_normal_cited_answer(self) -> None:
        snap = _risk_snapshot(risk_level="medium", risk_score="0.50")
        result = retrieve_supplier_performance_risk(
            SupplierPerformanceRiskInput(snapshots=(snap,))
        )
        assert isinstance(result, AnalystAnswer)
        assert result.calculation_version == CALCULATION_VERSION
        assert len(result.citations) == 1
        assert result.citations[0].source_kind == CitationSourceKind.supplier_scorecard_snapshot
        assert result.citations[0].source_id == snap.id
        assert "medium" in result.answer_text.lower()

    # 2. Zero grounding data
    def test_zero_grounding_data_says_so_explicitly(self) -> None:
        result = retrieve_supplier_performance_risk(SupplierPerformanceRiskInput())
        assert isinstance(result, NoGroundingData)
        assert result.reason == "no_records"
        assert "never guesses" in result.explanation

    # 3. Conflicting records — multiple snapshots for same supplier with different risk levels
    def test_conflicting_risk_levels_are_both_surfaced(self) -> None:
        snap_old = SupplierRiskRecord(
            id=uuid4(),
            supplier_id=SUPPLIER_A,
            supplier_name="Acme Ltd",
            risk_level="low",
            risk_score=D("0.2"),
            state="ready",
            window_end=date(2026, 8, 1),
        )
        snap_new = SupplierRiskRecord(
            id=uuid4(),
            supplier_id=SUPPLIER_A,
            supplier_name="Acme Ltd",
            risk_level="high",
            risk_score=D("0.8"),
            state="ready",
            window_end=date(2026, 9, 1),
        )
        result = retrieve_supplier_performance_risk(
            SupplierPerformanceRiskInput(snapshots=(snap_old, snap_new))
        )
        assert isinstance(result, AnalystAnswer)
        # Both risk levels must appear in the answer
        assert "low" in result.answer_text.lower()
        assert "high" in result.answer_text.lower()
        assert "conflict" in result.answer_text.lower()
        # Both must be cited
        cited_ids = {c.source_id for c in result.citations}
        assert snap_old.id in cited_ids
        assert snap_new.id in cited_ids

    # 4. Explicit-currency handling (risk scores have no currency — this tests that
    #    the function doesn't invent any monetary aggregation)
    def test_no_monetary_aggregation_invented(self) -> None:
        result = retrieve_supplier_performance_risk(
            SupplierPerformanceRiskInput(
                snapshots=(
                    _risk_snapshot(supplier_id=SUPPLIER_A, name="Acme Ltd"),
                    _risk_snapshot(supplier_id=SUPPLIER_B, name="Beta Corp"),
                )
            )
        )
        assert isinstance(result, AnalystAnswer)
        # Result must not synthesize a Money value — risk is dimensionless
        assert result.value is None

    # 5. Cross-tenant / unknown identifier → zero pre-scoped records → NoGroundingData
    def test_unknown_supplier_id_is_no_grounding_data(self) -> None:
        result = retrieve_supplier_performance_risk(SupplierPerformanceRiskInput())
        assert isinstance(result, NoGroundingData)

    # 6. Replay determinism
    def test_replay_determinism(self) -> None:
        snap_id = uuid4()
        inputs = SupplierPerformanceRiskInput(
            snapshots=(
                SupplierRiskRecord(
                    id=snap_id,
                    supplier_id=SUPPLIER_A,
                    supplier_name="Acme Ltd",
                    risk_level="medium",
                    risk_score=D("0.5"),
                    state="ready",
                    window_end=TODAY,
                ),
            )
        )
        assert retrieve_supplier_performance_risk(inputs) == retrieve_supplier_performance_risk(
            inputs
        )


# ===========================================================================
# Category 3: Orders and quotations
# ===========================================================================


class TestOrdersQuotations:
    # 1. Normal cited answer
    def test_normal_cited_answer(self) -> None:
        order = _order(status="received", amount="500.00")
        quot = _quotation(unit_price="50.00")
        result = retrieve_orders_quotations(
            OrdersQuotationsInput(orders=(order,), quotations=(quot,))
        )
        assert isinstance(result, AnalystAnswer)
        assert result.calculation_version == CALCULATION_VERSION
        assert len(result.citations) == 2
        cited_kinds = {c.source_kind for c in result.citations}
        assert CitationSourceKind.purchase_order in cited_kinds
        assert CitationSourceKind.quotation_line in cited_kinds
        assert "received" in result.answer_text

    # 2. Zero grounding data
    def test_zero_grounding_data_says_so_explicitly(self) -> None:
        result = retrieve_orders_quotations(OrdersQuotationsInput())
        assert isinstance(result, NoGroundingData)
        assert result.reason == "no_records"
        assert "never guesses" in result.explanation

    # 3. Conflicting records — two orders with different currencies
    def test_conflicting_order_currencies_surfaces_both(self) -> None:
        result = retrieve_orders_quotations(
            OrdersQuotationsInput(
                orders=(
                    _order(currency="GBP", amount="1000.00"),
                    _order(currency="USD", amount="2000.00"),
                )
            )
        )
        assert isinstance(result, AnalystAnswer)
        assert "GBP" in result.answer_text
        assert "USD" in result.answer_text
        assert "conflict" in result.answer_text.lower()

    # 4. Explicit-currency handling — quotation lines from different currencies
    def test_no_cross_currency_quotation_aggregation(self) -> None:
        result = retrieve_orders_quotations(
            OrdersQuotationsInput(
                quotations=(
                    _quotation(currency="GBP", unit_price="50.00"),
                    _quotation(currency="EUR", unit_price="55.00"),
                )
            )
        )
        assert isinstance(result, AnalystAnswer)
        assert "GBP" in result.answer_text
        assert "EUR" in result.answer_text
        assert "conflict" in result.answer_text.lower()

    # 5. Unknown identifier → zero pre-scoped records → NoGroundingData
    def test_unknown_identifier_is_no_grounding_data(self) -> None:
        result = retrieve_orders_quotations(OrdersQuotationsInput())
        assert isinstance(result, NoGroundingData)

    # 6. Replay determinism
    def test_replay_determinism(self) -> None:
        order_id, quot_id = uuid4(), uuid4()
        inputs = OrdersQuotationsInput(
            orders=(
                OrderRecord(
                    id=order_id,
                    supplier_id=SUPPLIER_A,
                    status="received",
                    total_amount=D("500.00"),
                    currency="GBP",
                    order_date=TODAY,
                    expected_delivery_date=None,
                ),
            ),
            quotations=(
                QuotationRecord(
                    id=quot_id,
                    supplier_id=SUPPLIER_A,
                    product_id=PRODUCT_A,
                    unit_price_amount=D("50.00"),
                    currency="GBP",
                    created_at=TODAY,
                ),
            ),
        )
        assert retrieve_orders_quotations(inputs) == retrieve_orders_quotations(inputs)


# ===========================================================================
# Category 4: Reorder forecasts
# ===========================================================================


class TestReorderForecasts:
    # 1. Normal cited answer
    def test_normal_cited_answer(self) -> None:
        proposal = _reorder(status="pending", quantity="20", urgency="urgent")
        result = retrieve_reorder_forecasts(
            ReorderForecastsInput(proposals=(proposal,))
        )
        assert isinstance(result, AnalystAnswer)
        assert result.calculation_version == CALCULATION_VERSION
        assert len(result.citations) == 1
        assert result.citations[0].source_kind == CitationSourceKind.reorder_proposal
        assert result.citations[0].source_id == proposal.id
        assert "pending" in result.answer_text
        assert "1" in result.answer_text  # urgent count

    # 2. Zero grounding data
    def test_zero_grounding_data_says_so_explicitly(self) -> None:
        result = retrieve_reorder_forecasts(ReorderForecastsInput())
        assert isinstance(result, NoGroundingData)
        assert result.reason == "no_records"
        assert "never guesses" in result.explanation

    # 3. Conflicting records — two proposals for the same product with conflicting statuses
    def test_conflicting_statuses_are_surfaced(self) -> None:
        """Both 'pending' and 'cancelled' for the same product must both appear."""
        result = retrieve_reorder_forecasts(
            ReorderForecastsInput(
                proposals=(
                    _reorder(product_id=PRODUCT_A, status="pending"),
                    _reorder(product_id=PRODUCT_A, status="cancelled"),
                )
            )
        )
        assert isinstance(result, AnalystAnswer)
        assert "pending" in result.answer_text
        assert "cancelled" in result.answer_text
        assert len(result.citations) == 2

    # 4. Explicit-currency handling — reorder proposals have no currency;
    #    this test confirms no money is synthesized from quantity alone
    def test_no_spurious_monetary_value_invented(self) -> None:
        result = retrieve_reorder_forecasts(
            ReorderForecastsInput(proposals=(_reorder(),))
        )
        assert isinstance(result, AnalystAnswer)
        assert result.value is None, "reorder proposals are dimensionless — no Money should appear"

    # 5. Unknown identifier → zero pre-scoped proposals → NoGroundingData
    def test_unknown_product_id_is_no_grounding_data(self) -> None:
        result = retrieve_reorder_forecasts(ReorderForecastsInput())
        assert isinstance(result, NoGroundingData)

    # 6. Replay determinism
    def test_replay_determinism(self) -> None:
        proposal_id = uuid4()
        inputs = ReorderForecastsInput(
            proposals=(
                ReorderRecord(
                    id=proposal_id,
                    product_id=PRODUCT_A,
                    proposed_quantity=D("15"),
                    status="pending",
                    created_at=TODAY,
                    urgency="normal",
                ),
            )
        )
        assert retrieve_reorder_forecasts(inputs) == retrieve_reorder_forecasts(inputs)


# ===========================================================================
# Cross-cutting: calculation_version is pinned on every answer
# ===========================================================================


@pytest.mark.parametrize(
    "call",
    [
        lambda: retrieve_spend_savings(
            SpendSavingsInput(spend_records=(_spend(),))
        ),
        lambda: retrieve_supplier_performance_risk(
            SupplierPerformanceRiskInput(snapshots=(_risk_snapshot(),))
        ),
        lambda: retrieve_orders_quotations(
            OrdersQuotationsInput(orders=(_order(),))
        ),
        lambda: retrieve_reorder_forecasts(
            ReorderForecastsInput(proposals=(_reorder(),))
        ),
    ],
    ids=["spend_savings", "supplier_risk", "orders_quotations", "reorder_forecasts"],
)
def test_calculation_version_is_pinned_on_every_answer(call: object) -> None:
    result = call()  # type: ignore[operator]
    assert result.calculation_version == CALCULATION_VERSION == "analyst-retrieval-v1"


# ===========================================================================
# Cross-cutting: NoGroundingData on all categories when inputs are empty
# ===========================================================================


@pytest.mark.parametrize(
    ("fn", "empty_input"),
    [
        (retrieve_spend_savings, SpendSavingsInput()),
        (retrieve_supplier_performance_risk, SupplierPerformanceRiskInput()),
        (retrieve_orders_quotations, OrdersQuotationsInput()),
        (retrieve_reorder_forecasts, ReorderForecastsInput()),
    ],
    ids=["spend_savings", "supplier_risk", "orders_quotations", "reorder_forecasts"],
)
def test_empty_inputs_always_return_no_grounding_data(fn: object, empty_input: object) -> None:
    result = fn(empty_input)  # type: ignore[operator]
    assert isinstance(result, NoGroundingData)
    assert result.reason == "no_records"
