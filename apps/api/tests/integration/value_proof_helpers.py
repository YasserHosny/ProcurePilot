from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import SmartCompareContext
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters
from procurepilot_api.modules.savings.schemas import Money, PurchaseOutcomeCreate, SavingRecord
from procurepilot_api.modules.savings.service import SavingsService


def purchase_payload(
    context: SmartCompareContext,
    *,
    actual: str = "8.0000",
) -> PurchaseOutcomeCreate:
    return PurchaseOutcomeCreate(
        workspace_product_id=context.product_id,
        supplier_id=context.supplier_ids[0],
        quantity=Decimal("10.000000"),
        base_unit="litre",
        unit_price=Money(amount=Decimal(actual) / Decimal("10.0000"), currency="GBP"),
        total_paid=Money(amount=Decimal(actual), currency="GBP"),
        delivery_result="delivered",
    )


def record_purchase(
    service: SavingsService,
    context: SmartCompareContext,
    *,
    actual: str = "8.0000",
) -> SavingRecord:
    return service.record_purchase(
        member=context.member,
        payload=purchase_payload(context, actual=actual),
    ).saving_record


def export_request(*, supplier_id: UUID | None = None) -> ExportCreate:
    return ExportCreate(
        kind="savings_ledger",
        format="xlsx",
        filters=ExportFilters(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            supplier_id=supplier_id,
        ),
    )


def fetch_savings(tenant_id: UUID) -> list[dict[str, object]]:
    with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from saving_record where tenant_id = %s order by recorded_at, id",
                (tenant_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def fetch_export_jobs(tenant_id: UUID) -> list[dict[str, object]]:
    with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from export_job where tenant_id = %s order by created_at desc, id desc",
                (tenant_id,),
            )
            return [dict(row) for row in cur.fetchall()]
