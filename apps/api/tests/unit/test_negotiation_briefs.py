from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from procurepilot_api.modules.offers.negotiation_briefs import (
    BriefBill,
    BriefContext,
    NegotiationBriefService,
    _brief_bills,
    _brief_evidence_refs,
    _evidence_ids,
)
from procurepilot_api.modules.offers.supplier_iq_v2 import (
    Alternative,
    OrderLine,
    Price,
    PurchaseOrder,
    ReceiptLine,
    SupplierRiskInput,
    calculate_supplier_risk,
)

S = UUID(int=1)
OTHER = UUID(int=2)
END = date(2026, 9, 20)


def _stamp(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), UTC)


def test_prepare_builds_ranked_source_linked_categories() -> None:
    orders: list[PurchaseOrder] = []
    receipts: list[ReceiptLine] = []
    prices: list[Price] = []
    alternatives: list[Alternative] = []
    for product_number in range(3):
        product = UUID(int=100 + product_number)
        for period, day in enumerate((END - timedelta(days=150), END - timedelta(days=30))):
            line_id = UUID(int=1000 + product_number * 10 + period)
            order_id = UUID(int=2000 + product_number * 10 + period)
            orders.append(
                PurchaseOrder(
                    order_id,
                    S,
                    day,
                    day,
                    "received",
                    Decimal("100"),
                    "GBP",
                    (OrderLine(line_id, product, "each", Decimal("1")),),
                )
            )
            receipts.append(
                ReceiptLine(
                    UUID(int=3000 + product_number * 10 + period),
                    order_id,
                    line_id,
                    Decimal("1"),
                    _stamp(day),
                )
            )
            prices.append(
                Price(
                    UUID(int=4000 + product_number * 10 + period),
                    S,
                    product,
                    "each",
                    "GBP",
                    Decimal(str(100 + period * 25)),
                    _stamp(day),
                )
            )
            alternatives.append(
                Alternative(
                    UUID(int=5000 + product_number * 10 + period),
                    OTHER,
                    product,
                    "each",
                    "GBP",
                    Decimal("90"),
                    _stamp(day),
                    day,
                    None,
                    True,
                )
            )
    snapshot = calculate_supplier_risk(
        SupplierRiskInput(
            supplier_id=S,
            window_start=END - timedelta(days=180),
            split_date=END - timedelta(days=90),
            window_end=END,
            purchase_orders=tuple(orders),
            receipts=tuple(receipts),
            prices=tuple(prices),
            alternatives=tuple(alternatives),
        )
    )
    context = BriefContext(
        supplier_id=S,
        as_of=END,
        orders=tuple(
            orders
            + [
                PurchaseOrder(
                    UUID(int=6000 + index),
                    S,
                    END - timedelta(days=index * 10),
                    END,
                    "received",
                    Decimal("10"),
                    "GBP",
                )
                for index in range(4)
            ]
        ),
        bills=(BriefBill(UUID(int=7000), "open", END - timedelta(days=5), Decimal("25"), "GBP"),),
    )
    draft = NegotiationBriefService.prepare(snapshot, context)
    assert {item.kind for item in draft.items} == {
        "price_trajectory",
        "alternatives",
        "service_performance",
        "concentration_volume",
        "payment_context",
        "purchase_pattern",
    }
    assert all(item.evidence_ids for item in draft.items)
    assert [item.rank for item in draft.items] == list(range(1, len(draft.items) + 1))
    assert draft.release_posture == "g3_unmet"


def test_payment_and_purchase_pattern_require_sufficient_evidence() -> None:
    context = BriefContext(supplier_id=S, as_of=END, orders=(), bills=())
    assert context.bills == ()


def test_brief_evidence_refs_preserve_typed_source_targets() -> None:
    evidence_id = UUID(int=8000)
    order_id = UUID(int=8001)

    class FakeCursor:
        def execute(self, query: str, params: tuple[UUID]) -> None:
            assert "supplier_scorecard_evidence" in query
            assert params == (UUID(int=8002),)

        def fetchall(self) -> list[dict[str, UUID | None]]:
            return [
                {
                    "id": evidence_id,
                    "purchase_order_id": order_id,
                    "delivery_receipt_id": None,
                    "landed_cost_id": None,
                    "three_way_match_id": None,
                    "synced_bill_id": None,
                    "workspace_product_id": None,
                    "delivery_quality_issue_id": None,
                    "supplier_commercial_term_id": None,
                }
            ]

    refs = _brief_evidence_refs(FakeCursor(), UUID(int=8002))  # type: ignore[arg-type]

    assert len(refs) == 1
    assert refs[0].evidence_id == evidence_id
    assert refs[0].source_kind == "purchase_order"
    assert refs[0].source_id == order_id


def test_brief_bills_reads_the_accounting_provider_status_column() -> None:
    bill_id = UUID(int=9000)

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, params: tuple[UUID]) -> None:
            assert "provider_status::text as status" in query
            assert params == (S,)

        def fetchall(self) -> list[dict[str, object]]:
            return [
                {
                    "id": bill_id,
                    "status": "open",
                    "due_date": END,
                    "remaining_balance_amount": Decimal("25.00"),
                    "remaining_balance_currency": "GBP",
                }
            ]

    class FakeConnection:
        def cursor(self, **_kwargs: object) -> FakeCursor:
            return FakeCursor()

    bills = _brief_bills(FakeConnection(), S)  # type: ignore[arg-type]

    assert bills == (BriefBill(bill_id, "open", END, Decimal("25.00"), "GBP"),)


def test_evidence_lookup_types_a_missing_metric_id_as_uuid() -> None:
    source_id = UUID(int=9100)

    class FakeCursor:
        def execute(self, query: str, params: tuple[object, ...]) -> None:
            assert "%s::uuid is null" in query
            assert params == (
                None,
                None,
                [source_id],
                [source_id],
                [source_id],
                [source_id],
                [source_id],
            )

        def fetchall(self) -> list[tuple[UUID]]:
            return []

    assert _evidence_ids(FakeCursor(), None, (source_id,)) == ()  # type: ignore[arg-type]
