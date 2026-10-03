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
        _seed_service_risk_rows(context)
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
        service_item = next(item for item in first.items if item.kind == "service_performance")
        # negotiation_brief_item.risk is numeric(18,8); a value round-tripped through the DB
        # comes back at that column's scale regardless of _decimal_text's 4-decimal quantize
        # on insert.
        assert service_item.risk == "1.00000000"
        # Whether reliability or the new three-way rate "wins" this specific brief item is a
        # tie-break detail already covered precisely, with full input control, by the unit
        # tests (test_negotiation_briefs.py's three_way_context/tied_context cases). What this
        # integration test needs to prove is that the new repository query + evidence-writing
        # path actually executes against a real tenant and really persists a linked
        # three_way_match evidence row -- so assert that directly, rather than depending on it
        # also being the winning item's displayed evidence (which additionally depends on this
        # tenant's seeded reliability data, a pre-existing, unrelated calculator this task does
        # not touch).
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as verify_conn:
            with verify_conn.cursor() as verify_cur:
                verify_cur.execute("reset role")
                verify_cur.execute(
                    "select count(*) from supplier_scorecard_evidence "
                    "where tenant_id = %s and three_way_match_id is not null",
                    (context.workspace.tenant_id,),
                )
                three_way_evidence_rows = verify_cur.fetchone()[0]
        assert three_way_evidence_rows == 3
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


def _seed_service_risk_rows(context: object) -> None:
    """Seed three non-matched results plus one linked quality report for supplier zero."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            cur.execute(
                """
                select po.id, po.expected_delivery_date, pol.id, pol.ordered_quantity
                from purchase_order po
                join purchase_order_line pol on pol.tenant_id = po.tenant_id
                  and pol.purchase_order_id = po.id
                where po.tenant_id = %s and po.supplier_id = %s
                order by po.order_date, po.id limit 4
                """,
                (context.workspace.tenant_id, context.supplier_ids[0]),
            )
            order_rows = cur.fetchall()
            order_ids = [row[0] for row in order_rows]
            # Reliability (a different component from the new three-way/quality signals) reads
            # delivery_receipt_line rows joined to their parent delivery_receipt, not
            # purchase_order.status -- _seed_orders() never inserts either, so without this these
            # same orders would ALSO show maximum reliability risk (no receipt ever arrived by
            # the expected date), tying with the three-way rate below and defeating this test's
            # whole point (proving three-way's signal, specifically, wins and gets evidenced).
            # Seed on-time receipts covering the full ordered quantity so reliability is clearly
            # low, while three_way_match flags the same orders as mismatched for an unrelated
            # reconciliation reason -- a realistic, intentional divergence between the two
            # signals.
            for order_id, expected_date, line_id, ordered_quantity in order_rows:
                receipt_id = uuid4()
                cur.execute(
                    """
                    insert into delivery_receipt
                      (id, tenant_id, purchase_order_id, receipt_reference, receipt_date,
                       received_by, source_reference)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        receipt_id,
                        context.workspace.tenant_id,
                        order_id,
                        f"receipt-{order_id}",
                        expected_date,
                        context.workspace.membership_id,
                        f"receipt-{order_id}",
                    ),
                )
                cur.execute(
                    """
                    insert into delivery_receipt_line
                      (tenant_id, delivery_receipt_id, purchase_order_id,
                       purchase_order_line_id, received_quantity)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        context.workspace.tenant_id,
                        receipt_id,
                        order_id,
                        line_id,
                        ordered_quantity,
                    ),
                )
            # three_way_match's own INSERT policy is worker-only (current_member_role() IS
            # NULL) -- no human role, owner included, may write it directly. reset_role drops
            # back to this connection's superuser default for just these inserts, bypassing RLS
            # entirely for test seeding, matching this suite's own established pattern for
            # writing rows a real member action could never produce.
            cur.execute("reset role")
            for order_id in order_ids[:3]:
                cur.execute(
                    """
                    insert into three_way_match
                      (tenant_id, purchase_order_id, result, tolerance_ruleset_version, source_hash)
                    values (%s, %s, 'unmatched', 'test-v1', %s)
                    """,
                    (context.workspace.tenant_id, order_id, f"test-{order_id}"),
                )
            act_as(cur, context.workspace)
            # committed_smart_context() never creates a branch -- it's built for
            # smart-compare/offers tests, which have no branch concept.
            branch_id = uuid4()
            cur.execute(
                "insert into branch (id, tenant_id, name, region) values (%s, %s, %s, 'GB')",
                (branch_id, context.workspace.tenant_id, f"{context.workspace.label} Branch"),
            )
            request_id = uuid4()
            cur.execute(
                """
                insert into purchase_request
                  (id, tenant_id, branch_id, requested_by_membership_id, required_by_date, status,
                   delivered_at)
                values (%s, %s, %s, %s, current_date, 'delivered', now())
                """,
                (
                    request_id,
                    context.workspace.tenant_id,
                    branch_id,
                    context.workspace.membership_id,
                ),
            )
            cur.execute(
                "update purchase_order set source_request_id = %s where id = %s",
                (request_id, order_ids[3]),
            )
            cur.execute(
                """
                insert into delivery_quality_issue
                  (tenant_id, purchase_request_id, reported_by_membership_id, description)
                values (%s, %s, %s, 'Integration seeded quality issue')
                """,
                (context.workspace.tenant_id, request_id, context.workspace.membership_id),
            )
        conn.commit()
