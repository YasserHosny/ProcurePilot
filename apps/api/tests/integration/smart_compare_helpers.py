from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import (
    ensure_quotation_reference_data,
    make_document,
    make_line,
    make_quotation,
    make_supplier,
)
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole

psycopg = pytest.importorskip("psycopg")


@dataclass(frozen=True)
class SmartCompareContext:
    workspace: Workspace
    product_id: UUID
    supplier_ids: list[UUID]

    @property
    def member(self) -> CurrentMember:
        return member_from_workspace(self.workspace)


@dataclass(frozen=True)
class CostedOffer:
    supplier_id: UUID
    quotation_id: UUID
    line_id: UUID
    match_decision_id: UUID
    landed_cost_id: UUID


def settings_for_test_db(monkeypatch: pytest.MonkeyPatch) -> Settings:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    return Settings()


def member_from_workspace(workspace: Workspace, *, role: MemberRole | None = None) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}-{workspace.role}@example.test",
        role=role or MemberRole(workspace.role),
    )


@contextmanager
def committed_smart_context(
    label: str,
    *,
    supplier_count: int = 2,
    preferred_supplier: bool = False,
) -> Iterator[SmartCompareContext]:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, label)
            supplier_ids = [
                make_supplier(cur, workspace, name=f"{label} Supplier {index}")
                for index in range(1, supplier_count + 1)
            ]
            for index, supplier_id in enumerate(supplier_ids, start=1):
                act_as(cur, workspace)
                cur.execute(
                    """
                    update supplier
                    set lead_time_days = %s, reliability_score = %s, status = 'active'
                    where id = %s
                    """,
                    (index * 2, Decimal("0.900"), supplier_id),
                )
            product_id = make_workspace_product(
                cur,
                workspace,
                name=f"{label} Product",
                supplier_id=supplier_ids[0] if preferred_supplier else None,
            )
        conn.commit()
    try:
        yield SmartCompareContext(
            workspace=workspace,
            product_id=product_id,
            supplier_ids=supplier_ids,
        )
    finally:
        cleanup_workspace(workspace)


def add_costed_offer(
    context: SmartCompareContext,
    *,
    supplier_id: UUID,
    amount: Decimal,
    status: str = "reviewed",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    recorded_at: datetime | None = None,
    confidence: Decimal = Decimal("0.9500"),
    quantity: Decimal = Decimal("1.000000"),
    product_id: UUID | None = None,
) -> CostedOffer:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    now = datetime.now(UTC)
    valid_from = valid_from or now - timedelta(days=30)
    recorded_at = recorded_at or now
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            document_id = make_document(cur, context.workspace)
            quotation_id = make_quotation(
                cur,
                context.workspace,
                document_id=document_id,
                supplier_id=supplier_id,
                status=status,
                arithmetic_status="reconciled",
            )
            line_id = make_line(cur, context.workspace, quotation_id)
            act_as(cur, context.workspace)
            decision_id = uuid4()
            cur.execute(
                """
                insert into match_decision
                  (id, tenant_id, quotation_line_id, matched_workspace_product_id,
                   outcome, is_automatic, confidence)
                values (%s, %s, %s, %s, 'no_match_new_product', true, %s)
                """,
                (
                    decision_id,
                    context.workspace.tenant_id,
                    line_id,
                    product_id or context.product_id,
                    confidence,
                ),
            )
            landed_cost_id = uuid4()
            normalised_quantity = quantity * Decimal("30.000000")
            raw_inputs = {
                "quantity": _quantity(quantity),
                "normalised_base_quantity": _quantity(normalised_quantity),
                "base_unit": "litre",
                "unit_price": {"amount": _money(amount), "currency": "GBP"},
                "vat_rate": "0.0000",
                "vat_amount": {"amount": "0.0000", "currency": "GBP"},
                "delivery_fee": {"amount": "0.0000", "currency": "GBP"},
                "discount": {"amount": "0.0000", "currency": "GBP"},
                "other_charges": {"amount": "0.0000", "currency": "GBP"},
            }
            cur.execute(
                """
                insert into landed_cost (
                  id, tenant_id, quotation_line_id, match_decision_id, quantity,
                  normalised_base_quantity, base_unit, unit_price_amount,
                  unit_price_currency, vat_amount, vat_currency, delivery_fee_amount,
                  delivery_fee_currency, discount_amount, discount_currency,
                  other_charges_amount, other_charges_currency, total_amount,
                  total_currency, raw_inputs, rule_version, valid_from, valid_to, recorded_at
                ) values (
                  %s, %s, %s, %s, %s, %s, 'litre', %s, 'GBP', 0, 'GBP', 0, 'GBP',
                  0, 'GBP', 0, 'GBP', %s, 'GBP', %s, 'landed-cost-v1', %s, %s, %s
                )
                """,
                (
                    landed_cost_id,
                    context.workspace.tenant_id,
                    line_id,
                    decision_id,
                    quantity,
                    normalised_quantity,
                    amount,
                    amount,
                    Jsonb(raw_inputs),
                    valid_from,
                    valid_to,
                    recorded_at,
                ),
            )
        conn.commit()
    return CostedOffer(
        supplier_id=supplier_id,
        quotation_id=quotation_id,
        line_id=line_id,
        match_decision_id=decision_id,
        landed_cost_id=landed_cost_id,
    )


def cleanup_workspace(workspace: Workspace) -> None:
    if not TEST_DATABASE_URL:
        return
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            reset_role(cur)
            # The owner-guard trigger refuses to delete the last active owner's membership row,
            # even via cascade from a tenant delete — same fix as test_import_atomicity.py.
            # Replica mode also disables FK cascade triggers, so value-proof children must be
            # removed explicitly before deleting the tenant.
            cur.execute("set session_replication_role = replica")
            try:
                cur.execute(
                    "delete from saving_record where tenant_id = %s",
                    (workspace.tenant_id,),
                )
                cur.execute(
                    "delete from purchase_record where tenant_id = %s",
                    (workspace.tenant_id,),
                )
                cur.execute("delete from export_job where tenant_id = %s", (workspace.tenant_id,))
                cur.execute(
                    "delete from billing_account where tenant_id = %s",
                    (workspace.tenant_id,),
                )
                cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
                cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
                cur.execute(
                    "delete from platform_invitation where email = %s", (_email(workspace),)
                )
            finally:
                cur.execute("set session_replication_role = default")
        conn.commit()


def fetch_basket_jobs(tenant_id: UUID) -> list[dict[str, object]]:
    if not TEST_DATABASE_URL:
        raise RuntimeError("TEST_DATABASE_URL is required")
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                select id, status, error
                from basket_split_job
                where tenant_id = %s
                order by created_at desc
                """,
                (tenant_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _email(workspace: Workspace) -> str:
    return f"{workspace.label}-{workspace.role}@example.test"


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _quantity(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)
