from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.offers.schemas import (
    Money,
    PriceHistoryMetric,
    PriceHistoryPoint,
    PriceHistoryResponse,
    PriceHistorySummary,
    ProductRef,
)


def test_price_history_contract_traces_metrics_to_landed_cost_rows() -> None:
    landed_cost_id = uuid4()
    product_id = uuid4()
    point = PriceHistoryPoint(
        landed_cost_id=landed_cost_id,
        workspace_product_id=product_id,
        supplier_id=uuid4(),
        supplier_name="Fresh",
        recorded_at=datetime.now(UTC),
        valid_from=datetime.now(UTC),
        normalised_unit_price=Money(amount="1.2500", currency="GBP"),
        landed_cost_total=Money(amount="12.5000", currency="GBP"),
        quantity="10.000000",
        base_unit="kg",
    )
    response = PriceHistoryResponse(
        product=ProductRef(id=product_id, tenant_name="Tomatoes"),
        window_months=6,
        points=[point],
        summary=PriceHistorySummary(
            last_paid=PriceHistoryMetric(
                value=point.normalised_unit_price,
                source_landed_cost_ids=[landed_cost_id],
            ),
            average_paid_rolling_window=None,
            best_price=None,
        ),
    )
    assert response.model_dump(mode="json")["summary"]["last_paid"][
        "source_landed_cost_ids"
    ] == [str(landed_cost_id)]
