from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from procurepilot_api.modules.accounting.three_way_match_service import (
    EvidenceLineProjection,
    EvidenceProjection,
    InvoiceLineProjection,
    MatchMoney,
    OrderLineProjection,
    OrderProjection,
    RawBillProjection,
    ThreeWayToleranceRuleset,
    evaluate_three_way_match,
)

ORDER_ID = UUID("00000000-0000-0000-0000-000000000001")
SUPPLIER_ID = UUID("00000000-0000-0000-0000-000000000002")
LINE_ID = UUID("00000000-0000-0000-0000-000000000003")


def _money(amount: str, currency: str = "GBP") -> MatchMoney:
    return MatchMoney(Decimal(amount), currency)


def _order(
    *,
    confirmation: EvidenceProjection | None = None,
    receipt: EvidenceProjection | None = None,
    currency: str = "GBP",
    provider_reference: str | None = "PO-PROVIDER-1",
    order_id: UUID = ORDER_ID,
) -> OrderProjection:
    line = OrderLineProjection(LINE_ID, 1, "2", _money("10", currency), description="Widget")
    return OrderProjection(
        id=order_id,
        supplier_id=SUPPLIER_ID,
        currency=currency,
        order_date=date(2026, 9, 19),
        lines=(line,),
        order_number="PO-1",
        provider_order_reference=provider_reference,
        confirmation=confirmation
        or EvidenceProjection(
            "available", ("confirmation-1",), (EvidenceLineProjection(LINE_ID, "2"),)
        ),
        receipt=receipt
        or EvidenceProjection("available", ("receipt-1",), (EvidenceLineProjection(LINE_ID, "2"),)),
    )


def _invoice(
    *, order_reference: str | None = "PO-PROVIDER-1", currency: str = "GBP"
) -> RawBillProjection:
    return RawBillProjection(
        provider_bill_id="bill-1",
        provider_vendor_id="vendor-1",
        supplier_id=SUPPLIER_ID,
        bill_date=date(2026, 9, 20),
        total=_money("20", currency),
        provider_order_reference=order_reference,
        lines=(InvoiceLineProjection("2", _money("10", currency), description="Widget"),),
    )


def _rules() -> ThreeWayToleranceRuleset:
    return ThreeWayToleranceRuleset("three-way-v1", Decimal("0"), _money("0.01"))


def test_exact_match_uses_provider_reference_first_and_is_replayable() -> None:
    result = evaluate_three_way_match(_invoice(), [_order()], _rules())

    assert result.result == "matched"
    assert result.order_id == ORDER_ID
    assert result.discrepancies == ()
    assert (
        result.source_hash == evaluate_three_way_match(_invoice(), [_order()], _rules()).source_hash
    )


def test_missing_evidence_is_partial_and_not_zero() -> None:
    order = _order(
        confirmation=EvidenceProjection("pending"), receipt=EvidenceProjection("pending")
    )

    result = evaluate_three_way_match(_invoice(), [order], _rules())

    assert result.result == "partial"
    assert {item.type for item in result.discrepancies} == {
        "missing_confirmation",
        "missing_receipt",
    }


def test_unavailable_evidence_is_unavailable() -> None:
    unavailable = EvidenceProjection("unavailable")
    result = evaluate_three_way_match(_invoice(), [_order(receipt=unavailable)], _rules())

    assert result.result == "unavailable"
    assert any(item.type == "missing_receipt" for item in result.discrepancies)


def test_currency_mismatch_is_never_accepted() -> None:
    result = evaluate_three_way_match(_invoice(currency="USD"), [_order()], _rules())

    assert result.result == "needs_review"
    assert any(item.type == "currency_mismatch" for item in result.discrepancies)


def test_currency_is_a_candidate_qualifier_before_ambiguity() -> None:
    result = evaluate_three_way_match(
        _invoice(order_reference=None),
        [_order(currency="GBP"), _order(currency="USD", order_id=UUID(int=4))],
        _rules(),
    )

    assert result.result == "matched"
    assert result.order_id == ORDER_ID


def test_zero_and_multiple_candidates_have_distinct_unresolved_outcomes() -> None:
    no_order = evaluate_three_way_match(_invoice(order_reference=None), [], _rules())
    ambiguous = evaluate_three_way_match(
        _invoice(order_reference=None),
        [_order(provider_reference=None), _order(provider_reference=None, order_id=UUID(int=4))],
        _rules(),
    )

    assert no_order.result == "unmatched"
    assert any(item.type == "invoice_without_order" for item in no_order.discrepancies)
    assert ambiguous.result == "needs_review"
    assert any(item.type == "ambiguous_order" for item in ambiguous.discrepancies)


def test_quantity_and_price_tolerances_are_explicit() -> None:
    invoice = _invoice()
    invoice = replace(
        invoice,
        lines=(InvoiceLineProjection("2.001", _money("10.005", "GBP"), description="Widget"),),
    )
    rules = ThreeWayToleranceRuleset("three-way-v2", Decimal("0.01"), _money("0.01"))

    result = evaluate_three_way_match(invoice, [_order()], rules)

    assert result.result == "matched"


def test_over_billing_is_distinguished_from_other_variance() -> None:
    invoice = replace(
        _invoice(),
        lines=(InvoiceLineProjection("3", _money("11", "GBP"), description="Widget"),),
    )
    result = evaluate_three_way_match(invoice, [_order()], _rules())

    assert {item.type for item in result.discrepancies} >= {
        "over_billed_quantity",
        "over_billed_price",
    }


def test_available_evidence_requires_lines_and_relevant_line_evidence() -> None:
    with pytest.raises(ValueError, match="at least one line"):
        EvidenceProjection("available", ("source-1",))

    irrelevant = EvidenceProjection(
        "available", ("source-1",), (EvidenceLineProjection(UUID(int=99), "2"),)
    )
    result = evaluate_three_way_match(
        _invoice(), [_order(confirmation=irrelevant, receipt=irrelevant)], _rules()
    )

    assert result.result == "needs_review"
    assert {item.type for item in result.discrepancies} >= {
        "missing_confirmation",
        "missing_receipt",
    }


def test_confirmation_quantity_and_price_are_compared_with_tolerances() -> None:
    confirmation = EvidenceProjection(
        "available",
        ("confirmation-1",),
        (EvidenceLineProjection(LINE_ID, "1.5", _money("10.02")),),
    )
    result = evaluate_three_way_match(_invoice(), [_order(confirmation=confirmation)], _rules())

    assert result.result == "needs_review"
    assert {item.type for item in result.discrepancies} >= {
        "over_billed_quantity",
        "over_billed_price",
    }


def test_duplicate_evidence_line_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        EvidenceProjection(
            "available",
            ("source-1",),
            (EvidenceLineProjection(LINE_ID, "1"), EvidenceLineProjection(LINE_ID, "1")),
        )


@pytest.mark.parametrize(
    "line_kwargs",
    [{"provider_line_reference": "missing"}, {"product_id": UUID(int=99)}],
)
def test_unresolved_explicit_line_identity_does_not_use_positional_fallback(
    line_kwargs: dict[str, object],
) -> None:
    invoice = replace(
        _invoice(),
        lines=(InvoiceLineProjection("2", _money("10"), **line_kwargs),),
    )

    result = evaluate_three_way_match(invoice, [_order()], _rules())

    assert result.result == "needs_review"
    assert any(item.type == "quantity_variance" for item in result.discrepancies)


def test_repeated_invoice_line_assignment_cannot_bypass_quantity_checks() -> None:
    invoice = replace(
        _invoice(),
        lines=(
            InvoiceLineProjection("2", _money("10"), description="Widget"),
            InvoiceLineProjection("2", _money("10"), description="Widget"),
        ),
    )

    result = evaluate_three_way_match(invoice, [_order()], _rules())

    assert result.result == "needs_review"
    assert any(item.type == "quantity_variance" for item in result.discrepancies)


def test_tolerance_currency_must_match_compared_currency() -> None:
    result = evaluate_three_way_match(
        _invoice(),
        [_order()],
        ThreeWayToleranceRuleset("v-usd", Decimal("0"), _money("0.01", "USD")),
    )

    assert result.result == "needs_review"
    assert any(item.type == "currency_mismatch" for item in result.discrepancies)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_values_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        MatchMoney(value, "GBP")
    with pytest.raises(ValueError, match="finite"):
        OrderLineProjection(LINE_ID, 1, value, _money("10"))
    with pytest.raises(ValueError, match="finite"):
        ThreeWayToleranceRuleset("bad", value, _money("0.01"))


def test_line_money_currencies_must_match_headers() -> None:
    with pytest.raises(ValueError, match="order currency"):
        OrderProjection(
            id=ORDER_ID,
            supplier_id=SUPPLIER_ID,
            currency="GBP",
            order_date=date(2026, 9, 19),
            lines=(OrderLineProjection(LINE_ID, 1, "2", _money("10", "USD")),),
        )
    with pytest.raises(ValueError, match="invoice total currency"):
        RawBillProjection(
            provider_bill_id="bill-1",
            provider_vendor_id="vendor-1",
            supplier_id=SUPPLIER_ID,
            bill_date=date(2026, 9, 20),
            total=_money("20", "GBP"),
            lines=(InvoiceLineProjection("2", _money("10", "USD")),),
        )


def test_provider_reference_tier_excludes_order_number_matches() -> None:
    provider_order = _order(provider_reference="provider-ref")
    display_order = _order(provider_reference="other-provider", order_id=UUID(int=4))
    invoice = replace(_invoice(), provider_order_reference="provider-ref")

    result = evaluate_three_way_match(invoice, [display_order, provider_order], _rules())

    assert result.result == "matched"
    assert result.order_id == ORDER_ID


def test_source_hash_changes_when_source_evidence_changes() -> None:
    first = evaluate_three_way_match(_invoice(), [_order()], _rules())
    changed_order = _order(
        receipt=EvidenceProjection(
            "available", ("receipt-2",), (EvidenceLineProjection(LINE_ID, "2"),)
        )
    )
    second = evaluate_three_way_match(_invoice(), [changed_order], _rules())

    assert first.result == second.result == "matched"
    assert first.source_hash != second.source_hash
