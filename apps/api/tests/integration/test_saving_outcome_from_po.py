"""Demo findings 22/23: record a purchase outcome from a PO, baselined on the last PO price."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, reset_role
from integration.smart_compare_helpers import (
    SmartCompareContext,
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.savings.schemas import (
    Money,
    PurchaseOutcomeCreate,
    PurchaseOutcomePrefillLine,
)
from procurepilot_api.modules.savings.service import SavingsService

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _make_order(
    context: SmartCompareContext,
    *,
    status: str,
    order_date: date,
    pack_price: str,
    packs: str = "2.000000",
    pack_size: str | None = "30.000000",
    base_unit: str = "litre",
    line_count: int = 1,
) -> tuple[UUID, UUID]:
    order_id, line_id = uuid4(), uuid4()
    total = Decimal(pack_price) * Decimal(packs) * line_count
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            reset_role(cur)
            cur.execute(
                "insert into purchase_order (id,tenant_id,order_number,supplier_id,status,"
                "order_date,total_amount,total_currency,tax_amount,tax_currency,"
                "source_reference,created_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,'GBP',0,'GBP','test',%s)",
                (
                    order_id,
                    context.workspace.tenant_id,
                    f"PO-OUTCOME-{uuid4().hex[:8]}",
                    context.supplier_ids[0],
                    status,
                    order_date,
                    total,
                    context.workspace.membership_id,
                ),
            )
            for number in range(1, line_count + 1):
                cur.execute(
                    "insert into purchase_order_line (id,tenant_id,purchase_order_id,line_number,"
                    "workspace_product_id,description,ordered_quantity,base_unit,"
                    "unit_price_amount,unit_price_currency,tax_amount,tax_currency,"
                    "line_total_amount,line_total_currency,pack_base_quantity) "
                    "values (%s,%s,%s,%s,%s,'Eggs carton',%s,%s,%s,'GBP',0,'GBP',%s,'GBP',%s)",
                    (
                        line_id if number == 1 else uuid4(),
                        context.workspace.tenant_id,
                        order_id,
                        number,
                        context.product_id,
                        Decimal(packs),
                        base_unit,
                        Decimal(pack_price),
                        Decimal(pack_price) * Decimal(packs),
                        None if pack_size is None else Decimal(pack_size),
                    ),
                )
        conn.commit()
    return order_id, line_id


def _payload(line: PurchaseOutcomePrefillLine) -> PurchaseOutcomeCreate:
    assert line.workspace_product_id is not None
    return PurchaseOutcomeCreate(
        workspace_product_id=line.workspace_product_id,
        purchase_order_line_id=line.purchase_order_line_id,
        quantity=line.quantity,
        base_unit=line.base_unit,
        unit_price=line.unit_price,
        total_paid=line.total_paid,
        delivery_result="ordered",
    )


def test_outcome_from_po_is_prefilled_in_base_units_and_baselined_on_last_po_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("po-outcome") as context:
        # A quote that would have been the old `last_paid` baseline.
        add_costed_offer(context, supplier_id=context.supplier_ids[1], amount=Decimal("1.0000"))
        _previous_order, previous_line = _make_order(
            context, status="received", order_date=date(2026, 9, 1), pack_price="172.0000"
        )
        # Newer, but a draft and a cancelled order are never a price that was paid.
        _make_order(context, status="draft", order_date=date(2026, 10, 10), pack_price="99.0000")
        _make_order(
            context, status="cancelled", order_date=date(2026, 10, 11), pack_price="98.0000"
        )
        order_id, line_id = _make_order(
            context, status="submitted", order_date=date(2026, 10, 15), pack_price="165.0000"
        )
        service = SavingsService(settings)

        prefill = service.purchase_prefill(member=context.member, purchase_order_id=order_id)

        assert prefill.delivery_result == "ordered"
        assert prefill.supplier_id == context.supplier_ids[0]
        [line] = prefill.lines
        assert line.purchase_order_line_id == line_id
        assert line.recordable is True
        assert line.quantity == Decimal("60.000000")  # 2 cartons x 30
        assert line.unit_price == Money(amount=Decimal("5.5000"), currency="GBP")
        assert line.total_paid == Money(amount=Decimal("330.0000"), currency="GBP")

        key = uuid4()
        created, was_created = service.record_purchase(
            member=context.member, payload=_payload(line), idempotency_key=key
        )

        assert was_created is True
        saving = created.saving_record
        assert created.purchase_record.purchase_order_line_id == line_id
        assert created.purchase_record.supplier_id == context.supplier_ids[0]
        assert saving.baseline_policy == "last_po_price"
        # The outcome's own order is excluded: the baseline is the previous received order.
        assert saving.baseline_source_po_line_ids == [previous_line]
        assert saving.baseline_value == Money(amount=Decimal("344.0000"), currency="GBP")
        assert saving.delta == Money(amount=Decimal("14.0000"), currency="GBP")
        assert saving.calculation_inputs["excluded_purchase_order_id"] == str(order_id)

        replay, replay_created = service.record_purchase(
            member=context.member, payload=_payload(line), idempotency_key=key
        )
        assert replay_created is False
        assert replay.saving_record.id == saving.id

        with pytest.raises(ConflictError) as duplicate:
            service.record_purchase(member=context.member, payload=_payload(line))
        assert duplicate.value.details == {"reason": "purchase_order_line_already_recorded"}

        again = service.purchase_prefill(member=context.member, purchase_order_id=order_id)
        assert again.lines[0].recordable is False
        assert again.lines[0].reason == "already_recorded"
        assert again.lines[0].recorded_saving_id == saving.id


def test_newer_lines_in_another_base_unit_do_not_hide_a_comparable_po_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex review on #173: a row limit applied before the base-unit check let newer lines in
    another unit push the comparable PO line out of the window."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("po-outcome-units") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[1], amount=Decimal("1.0000"))
        _older, comparable_line = _make_order(
            context, status="received", order_date=date(2026, 9, 1), pack_price="172.0000"
        )
        _make_order(
            context,
            status="received",
            order_date=date(2026, 10, 1),
            pack_price="1.0000",
            base_unit="kilogram",
            line_count=51,
        )
        created, _ = SavingsService(settings).record_purchase(
            member=context.member,
            payload=PurchaseOutcomeCreate(
                workspace_product_id=context.product_id,
                quantity=Decimal("60.000000"),
                base_unit="litre",
                unit_price=Money(amount=Decimal("5.5000"), currency="GBP"),
                total_paid=Money(amount=Decimal("330.0000"), currency="GBP"),
                delivery_result="delivered",
            ),
        )

        saving = created.saving_record
        assert saving.baseline_policy == "last_po_price"
        assert saving.baseline_source_po_line_ids == [comparable_line]
        assert saving.baseline_value == Money(amount=Decimal("344.0000"), currency="GBP")


def test_without_purchase_orders_the_quote_baseline_still_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("po-outcome-fallback") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("9.0000"))
        created, _ = SavingsService(settings).record_purchase(
            member=context.member,
            payload=PurchaseOutcomeCreate(
                workspace_product_id=context.product_id,
                quantity=Decimal("1.000000"),
                base_unit="litre",
                unit_price=Money(amount=Decimal("8.0000"), currency="GBP"),
                total_paid=Money(amount=Decimal("8.0000"), currency="GBP"),
                delivery_result="delivered",
            ),
        )

        assert created.saving_record.baseline_policy == "last_paid"
        assert created.saving_record.baseline_source_po_line_ids is None


def test_draft_order_cannot_be_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("po-outcome-draft") as context:
        order_id, line_id = _make_order(
            context, status="draft", order_date=date(2026, 10, 15), pack_price="165.0000"
        )
        service = SavingsService(settings)

        with pytest.raises(ConflictError):
            service.purchase_prefill(member=context.member, purchase_order_id=order_id)
        with pytest.raises(ConflictError):
            service.record_purchase(
                member=context.member,
                payload=PurchaseOutcomeCreate(
                    workspace_product_id=context.product_id,
                    purchase_order_line_id=line_id,
                    quantity=Decimal("60.000000"),
                    base_unit="litre",
                    unit_price=Money(amount=Decimal("5.5000"), currency="GBP"),
                    total_paid=Money(amount=Decimal("330.0000"), currency="GBP"),
                    delivery_result="ordered",
                ),
            )


def test_another_tenants_order_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with (
        committed_smart_context("po-outcome-owner") as owner,
        committed_smart_context("po-outcome-other") as other,
    ):
        order_id, line_id = _make_order(
            owner, status="received", order_date=date(2026, 10, 15), pack_price="165.0000"
        )
        service = SavingsService(settings)

        with pytest.raises(NotFoundError):
            service.purchase_prefill(member=other.member, purchase_order_id=order_id)
        with pytest.raises(NotFoundError):
            service.record_purchase(
                member=other.member,
                payload=PurchaseOutcomeCreate(
                    workspace_product_id=other.product_id,
                    purchase_order_line_id=line_id,
                    quantity=Decimal("60.000000"),
                    base_unit="litre",
                    unit_price=Money(amount=Decimal("5.5000"), currency="GBP"),
                    total_paid=Money(amount=Decimal("330.0000"), currency="GBP"),
                    delivery_result="ordered",
                ),
            )


def test_purchase_prefill_exposes_net_paid_and_separate_tax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("vat-prefill") as context:
        order, line = _make_order(
            context,
            status="submitted",
            order_date=date(2026, 10, 30),
            pack_price="12.0000",
            packs="100",
            pack_size="1",
        )
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            conn.execute(
                "update purchase_order_line set tax_amount=180, line_total_amount=1380 where id=%s",
                (line,),
            )
            conn.execute(
                "update purchase_order set tax_amount=180, total_amount=1380 where id=%s", (order,)
            )
            conn.commit()
        [prefill] = (
            SavingsService(settings)
            .purchase_prefill(member=context.member, purchase_order_id=order)
            .lines
        )
        assert prefill.total_paid == Money(amount=Decimal("1200.0000"), currency="GBP")
        assert prefill.tax == Money(amount=Decimal("180.0000"), currency="GBP")
