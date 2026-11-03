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


def test_latest_offer_window_is_per_supplier_across_rule_versions() -> None:
    import re

    from procurepilot_api.modules.offers.service import OFFER_READ_SQL

    partition = re.search(r"partition by (.*?)\s+order by", OFFER_READ_SQL, re.S)
    assert partition is not None
    assert partition.group(1).strip() == "md.matched_workspace_product_id, q.supplier_id"


def test_offer_projection_replays_v2_inclusive() -> None:
    from procurepilot_api.modules.offers.projection import project_landed_cost

    result = project_landed_cost(
        raw_inputs={
            "quantity": "350",
            "normalised_base_quantity": "350",
            "base_unit": "each",
            "unit_price": {"amount": "13.80", "currency": "SAR"},
            "vat_rate": "0.15",
            "delivery_fee": {"amount": "0", "currency": "SAR"},
            "discount": {"amount": "0", "currency": "SAR"},
            "prices_include_vat": True,
        },
        rule_version="landed-cost-v2",
        requested_quantity=Decimal("100"),
        pack_base_quantity=Decimal("1"),
    )
    assert result.total.amount == "1380.0000"


def test_offer_projection_prices_the_suppliers_own_pack_not_the_catalogue_pack() -> None:
    """P-157: a 9 L supplier pack bought against an 18 L catalogue pack is twice as many packs."""
    from procurepilot_api.modules.offers.projection import project_landed_cost

    result = project_landed_cost(
        raw_inputs={
            "quantity": "10",
            "normalised_base_quantity": "90",
            "base_unit": "litre",
            "unit_price": {"amount": "50.00", "currency": "SAR"},
            "vat_rate": "0",
            "delivery_fee": {"amount": "0", "currency": "SAR"},
            "discount": {"amount": "0", "currency": "SAR"},
        },
        rule_version="landed-cost-v1",
        requested_quantity=Decimal("180"),
        pack_base_quantity=Decimal("18"),
    )

    assert result.total.amount == "1000.0000"  # 180 L / 9 L = 20 supplier packs x 50
    assert result.normalised_unit_price.amount == "5.5556"


def test_offer_projection_falls_back_to_the_catalogue_pack_without_a_usable_quote_pack() -> None:
    from procurepilot_api.modules.offers.projection import project_landed_cost

    result = project_landed_cost(
        raw_inputs={
            "quantity": "0",
            "normalised_base_quantity": "0",
            "base_unit": "litre",
            "unit_price": {"amount": "50.00", "currency": "SAR"},
            "vat_rate": "0",
            "delivery_fee": {"amount": "0", "currency": "SAR"},
            "discount": {"amount": "0", "currency": "SAR"},
        },
        rule_version="landed-cost-v1",
        requested_quantity=Decimal("180"),
        pack_base_quantity=Decimal("18"),
    )

    assert result.total.amount == "500.0000"  # 180 L / 18 L = 10 packs x 50
