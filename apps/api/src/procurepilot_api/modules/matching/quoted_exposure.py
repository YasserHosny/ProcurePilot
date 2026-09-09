from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from procurepilot_api.modules.matching.schemas import QuotedExposureIssue
from procurepilot_api.modules.quotations.schemas import Money

FOUR_PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class QuotedExposureResult:
    total: Money | None
    issue: QuotedExposureIssue | None = None


def quoted_exposure(
    *,
    quantity: str | None,
    unit_price: Money | None,
    vat_rate: str | None = None,
    delivery_fee: Money | None = None,
    discount: Money | None = None,
) -> QuotedExposureResult:
    if quantity is None or unit_price is None:
        return QuotedExposureResult(total=None)

    adjustments = (money for money in (delivery_fee, discount) if money is not None)
    if any(money.currency != unit_price.currency for money in adjustments):
        return QuotedExposureResult(total=None, issue="currency_mismatch")

    line_net = (
        Decimal(quantity) * Decimal(unit_price.amount)
        + Decimal(delivery_fee.amount if delivery_fee else "0")
        - Decimal(discount.amount if discount else "0")
    )
    total = (line_net * (Decimal("1") + Decimal(vat_rate or "0"))).quantize(
        FOUR_PLACES
    )
    return QuotedExposureResult(
        total=Money(amount=format(total, "f"), currency=unit_price.currency)
    )
