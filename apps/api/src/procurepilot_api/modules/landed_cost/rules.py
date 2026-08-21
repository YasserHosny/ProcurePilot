from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

RULE_VERSION_V1 = "landed-cost-v1"
MONEY_QUANT = Decimal("0.0001")
QUANTITY_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class MoneyValue:
    amount: Decimal
    currency: str

    def quantized(self) -> MoneyValue:
        return MoneyValue(_money(self.amount), self.currency)


@dataclass(frozen=True)
class LandedCostInputs:
    quantity: Decimal
    normalised_base_quantity: Decimal
    base_unit: str
    unit_price: MoneyValue
    vat_rate: Decimal | None
    delivery_fee: MoneyValue
    discount: MoneyValue


@dataclass(frozen=True)
class LandedCostResult:
    quantity: Decimal
    normalised_base_quantity: Decimal
    base_unit: str
    unit_price: MoneyValue
    vat_rate: Decimal
    vat_amount: MoneyValue
    delivery_fee: MoneyValue
    discount: MoneyValue
    other_charges: MoneyValue
    total: MoneyValue
    raw_inputs: dict[str, object]
    rule_version: str = RULE_VERSION_V1


def compute_landed_cost(
    inputs: LandedCostInputs, *, rule_version: str = RULE_VERSION_V1
) -> LandedCostResult:
    if rule_version != RULE_VERSION_V1:
        raise ValueError(f"unsupported landed-cost rule version: {rule_version}")
    currency = inputs.unit_price.currency
    _require_same_currency(currency, inputs.delivery_fee, "delivery_fee")
    _require_same_currency(currency, inputs.discount, "discount")
    quantity = inputs.quantity.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
    normalised = inputs.normalised_base_quantity.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
    vat_rate = Decimal("0") if inputs.vat_rate is None else Decimal(str(inputs.vat_rate))
    unit_price = inputs.unit_price.quantized()
    delivery_fee = inputs.delivery_fee.quantized()
    discount = inputs.discount.quantized()
    vat_amount = MoneyValue(_money(unit_price.amount * quantity * vat_rate), currency)
    other_charges = MoneyValue(Decimal("0.0000"), currency)
    total = MoneyValue(
        _money(
            (unit_price.amount * quantity)
            + vat_amount.amount
            + delivery_fee.amount
            - discount.amount
        ),
        currency,
    )
    raw_inputs = {
        "quantity": _quantity_string(quantity),
        "normalised_base_quantity": _quantity_string(normalised),
        "base_unit": inputs.base_unit,
        "unit_price": _money_payload(unit_price),
        "vat_rate": _rate_string(vat_rate),
        "vat_amount": _money_payload(vat_amount),
        "delivery_fee": _money_payload(delivery_fee),
        "discount": _money_payload(discount),
        "other_charges": _money_payload(other_charges),
    }
    return LandedCostResult(
        quantity=quantity,
        normalised_base_quantity=normalised,
        base_unit=inputs.base_unit,
        unit_price=unit_price,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        delivery_fee=delivery_fee,
        discount=discount,
        other_charges=other_charges,
        total=total,
        raw_inputs=raw_inputs,
    )


def replay_landed_cost(raw_inputs: dict[str, object], *, rule_version: str) -> LandedCostResult:
    return compute_landed_cost(
        LandedCostInputs(
            quantity=Decimal(str(raw_inputs["quantity"])),
            normalised_base_quantity=Decimal(str(raw_inputs["normalised_base_quantity"])),
            base_unit=str(raw_inputs["base_unit"]),
            unit_price=_money_from_payload(raw_inputs["unit_price"]),
            vat_rate=Decimal(str(raw_inputs.get("vat_rate") or "0")),
            delivery_fee=_money_from_payload(raw_inputs["delivery_fee"]),
            discount=_money_from_payload(raw_inputs["discount"]),
        ),
        rule_version=rule_version,
    )


def _money_from_payload(payload: object) -> MoneyValue:
    if not isinstance(payload, dict):
        raise ValueError("money payload must be an object")
    return MoneyValue(Decimal(str(payload["amount"])), str(payload["currency"]))


def _require_same_currency(expected: str, money: MoneyValue, label: str) -> None:
    if money.currency != expected:
        raise ValueError(f"{label} currency must match unit_price currency")


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _money_payload(value: MoneyValue) -> dict[str, str]:
    quantized = value.quantized()
    return {"amount": format(quantized.amount, "f"), "currency": quantized.currency}


def _quantity_string(value: Decimal) -> str:
    return format(value.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP), "f")


def _rate_string(value: Decimal) -> str:
    return format(Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP), "f")
