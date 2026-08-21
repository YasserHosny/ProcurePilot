from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from procurepilot_api.modules.offers.service import _offer


def test_offer_projection_uses_row_data_and_never_fabricates_stock_signal() -> None:
    landed_cost_id = uuid4()
    row = {
        "id": landed_cost_id,
        "workspace_product_id": uuid4(),
        "supplier_id": uuid4(),
        "supplier_name": "Fresh Supplier",
        "quotation_line_id": uuid4(),
        "match_decision_id": uuid4(),
        "raw_inputs": {
            "quantity": "1.000000",
            "normalised_base_quantity": "30.000000",
            "base_unit": "litre",
            "unit_price": {"amount": "4.0000", "currency": "GBP"},
            "vat_rate": "0.0000",
            "delivery_fee": {"amount": "0.0000", "currency": "GBP"},
            "discount": {"amount": "0.0000", "currency": "GBP"},
        },
        "rule_version": "landed-cost-v1",
        "valid_from": datetime.now(UTC) - timedelta(days=1),
        "valid_to": datetime.now(UTC) + timedelta(days=10),
        "recorded_at": datetime.now(UTC),
        "base_unit": "litre",
        "match_confidence": Decimal("0.9500"),
        "lead_time_days": 3,
        "reliability_score": Decimal("0.900"),
        "pack_base_quantity": Decimal("30.000000"),
    }

    # requested quantity is expressed in the product's normalised base unit (litre here), the
    # same unit as pack_base_quantity — 30 litres is exactly this fixture's one pack.
    offer = _offer(row, quantity=Decimal("30.000000"))

    assert offer.id == landed_cost_id
    assert offer.landed_cost.amount == "4.0000"
    assert offer.normalised_unit_price.amount == "0.1333"
    assert offer.requested_quantity == "30.000000"
    assert offer.match_confidence == "0.9500"
    assert offer.stock_signal is None
