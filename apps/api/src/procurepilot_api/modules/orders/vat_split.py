"""Split printed gross pack prices without changing the printed line total.

Amounts retain the caller's currency; no currency conversion takes place here.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class VatInclusiveLine:
    net_unit_price: Decimal
    net_total: Decimal
    gross_total: Decimal
    tax: Decimal
    line_total: Decimal


def net_unit_price(gross: Decimal, rate: Decimal) -> Decimal:
    return (gross / (1 + rate)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def split_vat_inclusive_line(
    gross_unit: Decimal, quantity: Decimal, rate: Decimal
) -> VatInclusiveLine:
    net = net_unit_price(gross_unit, rate)
    net_total = (net * quantity).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    gross_total = (gross_unit * quantity).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    tax = gross_total - net_total
    return VatInclusiveLine(net, net_total, gross_total, tax, net_total + tax)
