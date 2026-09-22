"""Hosted integration coverage for atomic Supplier IQ v2 snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.offers import supplier_iq as supplier_iq_module
from procurepilot_api.modules.offers.supplier_iq import SupplierIqService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated hosted Postgres",
)


def test_recompute_persists_four_metrics_and_replays_by_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-v2-persist", supplier_count=2) as context:
        for supplier_id in context.supplier_ids:
            for amount in ("10.0000", "11.0000", "12.0000"):
                add_costed_offer(
                    context,
                    supplier_id=supplier_id,
                    amount=Decimal(amount),
                    recorded_at=datetime.now(UTC) - timedelta(days=1),
                )
        _seed_orders(context)
        service = SupplierIqService(settings)
        first_key = uuid4()
        first = service.recompute_all(member=context.member, idempotency_key=first_key)
        assert first.generated_snapshots == 2
        assert first.release_posture == "g3_unmet"

        replay = service.recompute_all(member=context.member, idempotency_key=first_key)
        assert replay == first
        second = service.recompute_all(member=context.member, idempotency_key=uuid4())
        assert second.generated_snapshots == 0
        risks = service.list_risks(member=context.member)
        assert len(risks.items) == 2
        with pytest.raises(UnprocessableEntityError):
            service.list_risks(member=context.member, cursor="invalid")

        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                cur.execute(
                    """
                    select count(*), count(distinct snapshot_id),
                           array_agg(metric_kind order by metric_kind)
                    from supplier_scorecard_metric scm
                    join supplier_scorecard_snapshot s
                      on s.tenant_id = scm.tenant_id and s.id = scm.snapshot_id
                    where s.supplier_id = any(%s)
                      and s.rule_version = 'supplier-scorecard-v2'
                    """,
                    (context.supplier_ids,),
                )
                metric_count, snapshot_count, metric_kinds = cur.fetchone()
                cur.execute(
                    """
                    select scm.value, count(sce.id), s.risk_score ? 'total'
                    from supplier_scorecard_metric scm
                    join supplier_scorecard_snapshot s
                      on s.tenant_id = scm.tenant_id and s.id = scm.snapshot_id
                    left join supplier_scorecard_evidence sce
                      on sce.tenant_id = scm.tenant_id and sce.metric_id = scm.id
                    where s.supplier_id = %s
                      and s.rule_version = 'supplier-scorecard-v2'
                      and scm.metric_kind = 'concentration'
                    group by scm.value, s.risk_score
                    """,
                    (context.supplier_ids[0],),
                )
                concentration_value, evidence_count, compatibility_total = cur.fetchone()
                cur.execute(
                    """
                    select
                      count(*) filter (where sce.purchase_order_id is not null),
                      count(*) filter (where sce.delivery_receipt_id is not null),
                      count(*) filter (where sce.landed_cost_id is not null),
                      count(*) filter (where sce.workspace_product_id is not null)
                    from supplier_scorecard_evidence sce
                    join supplier_scorecard_metric scm
                      on scm.tenant_id = sce.tenant_id and scm.id = sce.metric_id
                    join supplier_scorecard_snapshot s
                      on s.tenant_id = scm.tenant_id and s.id = scm.snapshot_id
                    where s.supplier_id = %s and s.rule_version = 'supplier-scorecard-v2'
                    """,
                    (context.supplier_ids[0],),
                )
                typed_evidence_counts = cur.fetchone()

        assert metric_count == 8
        assert snapshot_count == 2
        assert set(metric_kinds) == {
            "concentration",
            "price_drift",
            "reliability",
            "single_source_exposure",
        }
        assert concentration_value == Decimal("0.50000000")
        assert evidence_count >= 6
        assert compatibility_total is True
        assert all(count > 0 for count in typed_evidence_counts), typed_evidence_counts


def test_recompute_rolls_back_header_and_children_on_child_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-v2-rollback", supplier_count=1) as context:
        original = supplier_iq_module.persist_snapshot

        def fail_after_write(*args: object, **kwargs: object) -> object:
            original(*args, **kwargs)
            raise RuntimeError("forced scorecard failure")

        monkeypatch.setattr(supplier_iq_module, "persist_snapshot", fail_after_write)
        with pytest.raises(RuntimeError, match="forced scorecard failure"):
            SupplierIqService(settings).recompute_all(
                member=context.member, idempotency_key=uuid4()
            )

        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                cur.execute(
                    """
                    select
                      (select count(*) from supplier_scorecard_snapshot
                       where supplier_id = %s and rule_version = 'supplier-scorecard-v2'),
                      (select count(*) from supplier_scorecard_metric scm
                       join supplier_scorecard_snapshot s
                         on s.tenant_id = scm.tenant_id and s.id = scm.snapshot_id
                       where s.supplier_id = %s and s.rule_version = 'supplier-scorecard-v2')
                    """,
                    (context.supplier_ids[0], context.supplier_ids[0]),
                )
                assert cur.fetchone() == (0, 0)


def test_recompute_and_evidence_are_tenant_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-v2-tenant-a", supplier_count=1) as tenant_a:
        with committed_smart_context("supplier-iq-v2-tenant-b", supplier_count=1) as tenant_b:
            _seed_orders(tenant_a)
            _seed_orders(tenant_b)
            service = SupplierIqService(settings)
            assert (
                service.recompute_all(
                    member=tenant_a.member, idempotency_key=uuid4()
                ).generated_snapshots
                == 1
            )

            with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
                with conn.cursor() as cur:
                    act_as(cur, tenant_a.workspace)
                    cur.execute(
                        """
                        select count(distinct s.id), count(sce.id)
                        from supplier_scorecard_snapshot s
                        left join supplier_scorecard_metric scm
                          on scm.tenant_id = s.tenant_id and scm.snapshot_id = s.id
                        left join supplier_scorecard_evidence sce
                          on sce.tenant_id = scm.tenant_id and sce.metric_id = scm.id
                        where s.rule_version = 'supplier-scorecard-v2'
                        """
                    )
                    snapshot_count, evidence_count = cur.fetchone()
                    assert snapshot_count == 1
                    assert evidence_count > 0
                    act_as(cur, tenant_b.workspace)
                    cur.execute(
                        """
                        select count(*)
                        from supplier_scorecard_snapshot
                        where rule_version = 'supplier-scorecard-v2'
                        """
                    )
                    assert cur.fetchone() == (0,)


def _seed_orders(context: object) -> None:
    from datetime import date, timedelta

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            for supplier_index, supplier_id in enumerate(context.supplier_ids):
                for order_index in range(3):
                    order_id = uuid4()
                    line_id = uuid4()
                    receipt_id = uuid4()
                    receipt_line_id = uuid4()
                    order_date = date.today() - timedelta(days=30 + order_index)
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
                            context.product_id,
                        ),
                    )
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
                            f"receipt-{receipt_id}",
                            expected_date - timedelta(days=1),
                            context.workspace.membership_id,
                            f"test-{receipt_id}",
                        ),
                    )
                    cur.execute(
                        """
                        insert into delivery_receipt_line
                          (id, tenant_id, delivery_receipt_id, purchase_order_id,
                           purchase_order_line_id, received_quantity)
                        values (%s, %s, %s, %s, %s, 1)
                        """,
                        (
                            receipt_line_id,
                            context.workspace.tenant_id,
                            receipt_id,
                            order_id,
                            line_id,
                        ),
                    )
        conn.commit()
