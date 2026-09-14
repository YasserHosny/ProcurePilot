from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.smart_compare_helpers import (
    SmartCompareContext,
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.offers.supplier_iq import SupplierIqService

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_supplier_scorecard_metrics_trace_to_seeded_source_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-trace") as context:
        supplier_offer_ids = [
            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[0],
                amount=Decimal(amount),
            ).landed_cost_id
            for amount in ("10.0000", "11.0000", "12.0000")
        ]
        competitor_offer_ids = [
            add_costed_offer(
                context,
                supplier_id=context.supplier_ids[1],
                amount=Decimal(amount),
            ).landed_cost_id
            for amount in ("8.0000", "9.0000", "10.0000")
        ]
        purchase_ids = [
            _insert_purchase_record(context, "delivered", Decimal("10.0000")),
            _insert_purchase_record(context, "partially_delivered", Decimal("20.0000")),
            _insert_purchase_record(context, "disputed", Decimal("30.0000")),
        ]
        other_purchase_ids = [
            _insert_purchase_record(
                context,
                "delivered",
                Decimal("15.0000"),
                supplier_id=context.supplier_ids[1],
            ),
            _insert_purchase_record(
                context,
                "delivered",
                Decimal("25.0000"),
                supplier_id=context.supplier_ids[1],
            ),
        ]
        saving_ids = [
            _insert_saving_record(context, purchase_ids[0], Decimal("10.0000")),
            _insert_saving_record(context, purchase_ids[1], Decimal("20.0000")),
        ]
        other_saving_id = _insert_saving_record(
            context,
            other_purchase_ids[0],
            Decimal("30.0000"),
            supplier_id=context.supplier_ids[1],
        )
        quality_issue_id = _insert_quality_issue(context, supplier_offer_ids[0])

        scorecard = SupplierIqService(settings).get_scorecard(
            member=context.member,
            supplier_id=context.supplier_ids[0],
        )

        assert scorecard.supplier_id == context.supplier_ids[0]
        assert scorecard.window_start <= date.today() <= scorecard.window_end
        assert scorecard.metrics["fulfilment_rate"].value == "0.5000"
        assert scorecard.metrics["quality_score"].value == "0.6667"
        assert scorecard.metrics["spend_exposure"].value == "0.6000"
        assert scorecard.metrics["savings_contribution"].value == "0.5000"
        assert set(scorecard.metrics["fulfilment_rate"].source_ids) == set(purchase_ids)
        assert quality_issue_id in scorecard.metrics["quality_score"].source_ids
        assert set(supplier_offer_ids).issubset(
            set(scorecard.metrics["price_competitiveness"].source_ids)
        )
        assert set(competitor_offer_ids).issubset(
            set(scorecard.metrics["price_competitiveness"].source_ids)
        )
        assert set(scorecard.metrics["savings_contribution"].source_ids) == set(saving_ids)
        assert other_saving_id not in scorecard.metrics["savings_contribution"].source_ids
        assert scorecard.source_counts["purchase_record"] == 3
        assert scorecard.source_counts["tenant_purchase_record"] == 5
        assert scorecard.source_counts["delivery_quality_issue"] == 1
        assert _snapshot_count(context, context.supplier_ids[0]) == 1


def test_supplier_scorecard_honours_requested_window_months(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-window") as context:
        scorecard = SupplierIqService(settings).get_scorecard(
            member=context.member,
            supplier_id=context.supplier_ids[0],
            window_months=3,
        )

        assert 88 <= (scorecard.window_end - scorecard.window_start).days <= 93


def test_cross_tenant_supplier_scorecard_reference_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("supplier-iq-alpha") as alpha:
        with committed_smart_context("supplier-iq-beta") as beta:
            with pytest.raises(NotFoundError):
                SupplierIqService(settings).get_scorecard(
                    member=alpha.member,
                    supplier_id=beta.supplier_ids[0],
                )


def _insert_purchase_record(
    context: SmartCompareContext,
    delivery_result: str,
    total_paid: Decimal,
    *,
    supplier_id: UUID | None = None,
) -> UUID:
    purchase_id = uuid4()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            cur.execute(
                """
                insert into purchase_record (
                  id,
                  tenant_id,
                  workspace_product_id,
                  supplier_id,
                  recorded_by,
                  quantity,
                  base_unit,
                  unit_price_amount,
                  unit_price_currency,
                  total_paid_amount,
                  total_paid_currency,
                  delivery_result,
                  ordered_at,
                  delivered_at,
                  recorded_at
                )
                values (%s, %s, %s, %s, %s, 1.000000, 'litre', %s, 'GBP', %s,
                        'GBP', %s, %s, %s, %s)
                """,
                (
                    purchase_id,
                    context.workspace.tenant_id,
                    context.product_id,
                    supplier_id or context.supplier_ids[0],
                    context.workspace.membership_id,
                    total_paid,
                    total_paid,
                    delivery_result,
                    datetime.now(UTC) - timedelta(days=2),
                    datetime.now(UTC) - timedelta(days=1),
                    datetime.now(UTC),
                ),
            )
        conn.commit()
    return purchase_id


def _insert_saving_record(
    context: SmartCompareContext,
    purchase_record_id: UUID,
    delta: Decimal,
    *,
    supplier_id: UUID | None = None,
) -> UUID:
    saving_id = uuid4()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            cur.execute(
                """
                insert into saving_record (
                  id,
                  tenant_id,
                  purchase_record_id,
                  workspace_product_id,
                  supplier_id,
                  baseline_policy,
                  baseline_source_landed_cost_ids,
                  baseline_value_amount,
                  baseline_value_currency,
                  actual_value_amount,
                  actual_value_currency,
                  delta_amount,
                  delta_currency,
                  calculation_version,
                  calculation_inputs,
                  recorded_by
                )
                values (%s, %s, %s, %s, %s, 'last_paid', '{}', %s, 'GBP',
                        %s, 'GBP', %s, 'GBP', 'supplier-iq-test-v1', %s, %s)
                """,
                (
                    saving_id,
                    context.workspace.tenant_id,
                    purchase_record_id,
                    context.product_id,
                    supplier_id or context.supplier_ids[0],
                    delta + Decimal("10.0000"),
                    Decimal("10.0000"),
                    delta,
                    Jsonb({"source": "supplier_iq_integration_test"}),
                    context.workspace.membership_id,
                ),
            )
        conn.commit()
    return saving_id


def _insert_quality_issue(context: SmartCompareContext, landed_cost_id: UUID) -> UUID:
    issue_id = uuid4()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            act_as(cur, context.workspace)
            branch_id = uuid4()
            request_id = uuid4()
            line_id = uuid4()
            cur.execute(
                "insert into branch (id, tenant_id, name, region) values (%s, %s, %s, 'GB')",
                (branch_id, context.workspace.tenant_id, "Supplier IQ Branch"),
            )
            cur.execute(
                """
                insert into purchase_request (
                  id,
                  tenant_id,
                  branch_id,
                  requested_by_membership_id,
                  required_by_date,
                  status,
                  delivered_at
                )
                values (%s, %s, %s, %s, %s, 'delivered', %s)
                """,
                (
                    request_id,
                    context.workspace.tenant_id,
                    branch_id,
                    context.workspace.membership_id,
                    date.today(),
                    datetime.now(UTC),
                ),
            )
            cur.execute(
                """
                insert into purchase_request_line (
                  id,
                  tenant_id,
                  purchase_request_id,
                  workspace_product_id,
                  quantity,
                  estimated_unit_price_amount,
                  estimated_unit_price_currency,
                  estimated_unit_price_source_landed_cost_id,
                  estimated_at
                )
                values (%s, %s, %s, %s, 1.000000, 10.0000, 'GBP', %s, %s)
                """,
                (
                    line_id,
                    context.workspace.tenant_id,
                    request_id,
                    context.product_id,
                    landed_cost_id,
                    datetime.now(UTC),
                ),
            )
            cur.execute(
                """
                insert into delivery_quality_issue (
                  id,
                  tenant_id,
                  purchase_request_id,
                  reported_by_membership_id,
                  description
                )
                values (%s, %s, %s, %s, 'Damaged packaging')
                """,
                (
                    issue_id,
                    context.workspace.tenant_id,
                    request_id,
                    context.workspace.membership_id,
                ),
            )
        conn.commit()
    return issue_id


def _snapshot_count(context: SmartCompareContext, supplier_id: UUID) -> int:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            act_as(cur, context.workspace)
            cur.execute(
                """
                select count(*) as snapshot_count
                from supplier_scorecard_snapshot
                where supplier_id = %s
                """,
                (supplier_id,),
            )
            row = cur.fetchone()
    return int(row["snapshot_count"])
