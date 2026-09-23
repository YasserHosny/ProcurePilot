"""Hosted integration coverage for persisted negotiation briefs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, make_workspace_product
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.modules.offers.negotiation_briefs import NegotiationBriefService
from procurepilot_api.modules.offers.supplier_iq import SupplierIqService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated hosted Postgres",
)


def test_prepare_is_idempotent_and_actions_are_append_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("negotiation-brief", supplier_count=2) as context:
        product_ids = [context.product_id, *_seed_extra_products(context, count=2)]
        for supplier_id in context.supplier_ids:
            for index, product_id in enumerate(product_ids):
                # price_drift and single_source (supplier_iq_v2.py) both require signal
                # across >= 3 distinct products before they'll report a risk value — a
                # single repriced product isn't enough evidence, by design (see
                # _component()'s and _prices()'s own >= 3 sample/product gates). A
                # baseline price (before the window's split date) paired with a current
                # price (after it), for each of >= 3 products, is what clears that gate.
                add_costed_offer(
                    context,
                    supplier_id=supplier_id,
                    product_id=product_id,
                    amount=Decimal("10.0000") + index,
                    recorded_at=datetime.now(UTC) - timedelta(days=120),
                )
                add_costed_offer(
                    context,
                    supplier_id=supplier_id,
                    product_id=product_id,
                    amount=Decimal("11.0000") + index,
                    recorded_at=datetime.now(UTC) - timedelta(days=1),
                )
        _seed_orders(context, product_ids)
        SupplierIqService(settings).recompute_all(member=context.member, idempotency_key=uuid4())

        service = NegotiationBriefService(settings)
        prepare_key = uuid4()
        first = service.prepare_for_supplier(
            member=context.member,
            supplier_id=context.supplier_ids[0],
            idempotency_key=prepare_key,
        )
        replay = service.prepare_for_supplier(
            member=context.member,
            supplier_id=context.supplier_ids[0],
            idempotency_key=prepare_key,
        )

        assert replay.id == first.id
        assert first.release_posture == "g3_unmet"
        assert first.items
        assert all(item.evidence_ids for item in first.items)
        listed = service.list(member=context.member)
        assert [item.id for item in listed.items] == [first.id]
        assert service.get(member=context.member, brief_id=first.id).id == first.id

        acknowledge_key = uuid4()
        acknowledged = service.acknowledge(
            member=context.member,
            brief_id=first.id,
            idempotency_key=acknowledge_key,
        )
        assert acknowledged.status == "acknowledged"
        assert (
            service.acknowledge(
                member=context.member,
                brief_id=first.id,
                idempotency_key=acknowledge_key,
            ).status
            == "acknowledged"
        )

        dismiss_key = uuid4()
        dismissed = service.dismiss(
            member=context.member,
            brief_id=first.id,
            idempotency_key=dismiss_key,
            reason="Needs current supplier confirmation",
        )
        assert dismissed.status == "dismissed"

        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                cur.execute(
                    """
                    select count(*), count(distinct item_id)
                    from negotiation_brief_item_evidence link
                    join negotiation_brief_item item
                      on item.tenant_id = link.tenant_id and item.id = link.item_id
                    where item.brief_id = %s
                    """,
                    (first.id,),
                )
                evidence_count, item_count = cur.fetchone()
                cur.execute(
                    "select count(*) from negotiation_brief_action where brief_id = %s",
                    (first.id,),
                )
                action_count = cur.fetchone()[0]

        assert evidence_count >= item_count > 0
        assert action_count == 2


def _seed_extra_products(context: object, *, count: int) -> list:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            product_ids = [
                make_workspace_product(
                    cur, context.workspace, name=f"{context.workspace.label} Product {index}"
                )
                for index in range(1, count + 1)
            ]
        conn.commit()
    return product_ids


def _seed_orders(context: object, product_ids: list) -> None:
    from datetime import date

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            for supplier_index, supplier_id in enumerate(context.supplier_ids):
                for order_index in range(4):
                    order_id = uuid4()
                    line_id = uuid4()
                    order_date = date.today() - timedelta(days=30 + order_index * 7)
                    expected_date = date.today() - timedelta(days=5 + order_index)
                    cur.execute(
                        """
                        insert into purchase_order
                          (id, tenant_id, order_number, supplier_id, status, order_date,
                           expected_delivery_date, total_amount, total_currency, tax_amount,
                           tax_currency, source_reference, created_by)
                        values (%s, %s, %s, %s, 'received', %s, %s, 10, 'GBP', 0,
                                'GBP', %s, %s)
                        """,
                        (
                            order_id,
                            context.workspace.tenant_id,
                            f"{context.workspace.label}-{supplier_index}-{order_index}",
                            supplier_id,
                            order_date,
                            expected_date,
                            f"test-{order_id}",
                            context.workspace.membership_id,
                        ),
                    )
                    cur.execute(
                        """
                        insert into purchase_order_line
                          (id, tenant_id, purchase_order_id, line_number, workspace_product_id,
                           description, ordered_quantity, base_unit, unit_price_amount,
                           unit_price_currency, tax_amount, tax_currency, line_total_amount,
                           line_total_currency)
                        values (%s, %s, %s, 1, %s, 'test product', 1, 'litre', 10, 'GBP',
                                0, 'GBP', 10, 'GBP')
                        """,
                        (
                            line_id,
                            context.workspace.tenant_id,
                            order_id,
                            product_ids[order_index % len(product_ids)],
                        ),
                    )
        conn.commit()
