from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from procurepilot_api.modules.landed_cost.rules import (
    MONEY_QUANT,
    QUANTITY_QUANT,
    replay_landed_cost,
)
from procurepilot_api.modules.offers.schemas import Money


@dataclass(frozen=True)
class ProjectedCost:
    total: Money
    normalised_unit_price: Money
    requested_quantity: str
    normalised_base_quantity: str


def project_landed_cost(
    *,
    raw_inputs: dict[str, object],
    rule_version: str,
    requested_quantity: Decimal,
    pack_base_quantity: Decimal,
) -> ProjectedCost:
    # requested_quantity is expressed in the product's normalised base unit (kg/litre/each) —
    # the same unit every other figure on the compare screen (normalised_unit_price, base_unit)
    # is already in — so convert it to the number of original supplier pack units the landed-cost
    # formula itself prices against, rather than treating it as a pack count.
    requested = requested_quantity.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
    packs_needed = (requested / pack_base_quantity).quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
    projected_inputs = dict(raw_inputs)
    projected_inputs["quantity"] = _quantity_string(packs_needed)
    projected_inputs["normalised_base_quantity"] = _quantity_string(requested)
    result = replay_landed_cost(projected_inputs, rule_version=rule_version)
    unit_amount = (result.total.amount / requested).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return ProjectedCost(
        total=Money(amount=format(result.total.amount, "f"), currency=result.total.currency),
        normalised_unit_price=Money(
            amount=format(unit_amount, "f"),
            currency=result.total.currency,
        ),
        requested_quantity=_quantity_string(requested),
        normalised_base_quantity=_quantity_string(requested),
    )


def _quantity_string(value: Decimal) -> str:
    return format(value.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP), "f")
