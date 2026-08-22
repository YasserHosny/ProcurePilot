from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.landed_cost.schemas import LandedCost, Money


def test_landed_cost_contract_exposes_money_pairs_rule_version_and_raw_inputs() -> None:
    payload = LandedCost(
        id=uuid4(),
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        quantity="10.000000",
        normalised_base_quantity="60.000000",
        base_unit="each",
        unit_price=Money(amount="12.5000", currency="GBP"),
        vat_amount=Money(amount="25.0000", currency="GBP"),
        delivery_fee=Money(amount="5.0000", currency="GBP"),
        discount=Money(amount="10.0000", currency="GBP"),
        other_charges=Money(amount="0.0000", currency="GBP"),
        total=Money(amount="145.0000", currency="GBP"),
        raw_inputs={
            "quantity": "10.000000",
            "normalised_base_quantity": "60.000000",
            "base_unit": "each",
            "unit_price": {"amount": "12.5000", "currency": "GBP"},
            "vat_rate": "0.2000",
            "vat_amount": {"amount": "25.0000", "currency": "GBP"},
            "delivery_fee": {"amount": "5.0000", "currency": "GBP"},
            "discount": {"amount": "10.0000", "currency": "GBP"},
            "other_charges": {"amount": "0.0000", "currency": "GBP"},
        },
        rule_version="landed-cost-v1",
        valid_from=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["total"] == {"amount": "145.0000", "currency": "GBP"}
    assert dumped["rule_version"] == "landed-cost-v1"
    assert dumped["raw_inputs"]["other_charges"]["amount"] == "0.0000"
