"""Authoritative round-1 packs and SAR prices (ADR-020), shared by spec 024 tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import make_line, make_quotation, make_supplier
from integration.smart_compare_helpers import cleanup_workspace, member_from_workspace
from procurepilot_api.deps import CurrentMember

# name, pack size, base unit, requested packs, DH-26-1252, WF/2026/0781
ROUND1 = (
    ("أرز بسمتي", 10, "kilogram", 25, 85, 87),
    ("زيت دوار الشمس", 18, "litre", 6, 151, 145),
    ("سكر أبيض", 10, "kilogram", 12, 39, 35),
    ("دقيق", 45, "kilogram", 8, 81, 84),
)


@dataclass(frozen=True)
class Round1Rfq:
    workspace: Workspace
    rfq_id: UUID
    branch_id: UUID
    product_ids: list[UUID]
    supplier_ids: list[UUID]
    quotation_ids: list[UUID]
    response_ids: list[UUID]

    @property
    def member(self) -> CurrentMember:
        return member_from_workspace(self.workspace)

    @property
    def split_total(self) -> Decimal:
        return sum((Decimal(row[3]) * min(row[4:]) for row in ROUND1), Decimal(0))


@contextmanager
def round1_rfq() -> Iterator[Round1Rfq]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "round1")
            cur.execute(
                "insert into supported_currency (code,label_en,label_ar) "
                "values ('SAR','Saudi riyal','ريال سعودي') on conflict do nothing"
            )
            cur.execute("update tenant set currency = 'SAR' where id = %s", (workspace.tenant_id,))
            products = []
            for name, size, unit, *_ in ROUND1:
                product_id = make_workspace_product(cur, workspace, name=name)
                products.append(product_id)
                reset_role(cur)
                cur.execute(
                    "update canonical_product set base_unit = %s where id = "
                    "(select canonical_product_id from workspace_product where id = %s)",
                    (unit, product_id),
                )
                cur.execute(
                    "update pack_definition set pack_count = 1, unit_size = %s "
                    "where workspace_product_id = %s",
                    (size, product_id),
                )
            suppliers = [make_supplier(cur, workspace, name=name) for name in ("الذهبي", "الوفرة")]
            rfq_id, branch_id = uuid4(), uuid4()
            cur.execute(
                "insert into branch (id,tenant_id,name) values (%s,%s,'Round 1')",
                (branch_id, workspace.tenant_id),
            )
            cur.execute(
                "insert into rfq (id,tenant_id,created_by_membership_id,status,"
                "needed_by_date,idempotency_key) values (%s,%s,%s,'responded',"
                "current_date+7,%s)",
                (rfq_id, workspace.tenant_id, workspace.membership_id, uuid4()),
            )
            for position, (product_id, row) in enumerate(zip(products, ROUND1, strict=True)):
                cur.execute(
                    "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,"
                    "quantity,position) values (%s,%s,%s,%s,%s)",
                    (workspace.tenant_id, rfq_id, product_id, row[3], position),
                )
            quotations, responses = [], []
            for index, supplier_id in enumerate(suppliers):
                quotation_id = make_quotation(
                    cur,
                    workspace,
                    supplier_id=supplier_id,
                    status="reviewed",
                    arithmetic_status="reconciled",
                )
                quotations.append(quotation_id)
                cur.execute("update quotation set currency = 'SAR' where id = %s", (quotation_id,))
                for position, (product_id, row) in enumerate(zip(products, ROUND1, strict=True), 1):
                    name, size, unit, packs = row[:4]
                    price = row[4 + index]
                    line_id = make_line(cur, workspace, quotation_id)
                    cur.execute(
                        "update quotation_line set line_number=%s,original_text=%s,"
                        "quantity=%s,pack_count=1,unit_size=%s,pack_unit=%s,"
                        "unit_price_amount=%s,unit_price_currency='SAR' where id=%s",
                        (position + 1, name, packs, size, unit, price, line_id),
                    )
                    decision_id = uuid4()
                    cur.execute(
                        "insert into match_decision (id,tenant_id,quotation_line_id,"
                        "matched_workspace_product_id,outcome,is_automatic,confidence) "
                        "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                        (decision_id, workspace.tenant_id, line_id, product_id),
                    )
                    reset_role(cur)
                    cur.execute(
                        """
                        insert into landed_cost (
                            tenant_id,quotation_line_id,match_decision_id,quantity,
                            normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,
                            vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,
                            discount_amount,discount_currency,other_charges_amount,
                            other_charges_currency,total_amount,total_currency,raw_inputs,
                            rule_version,valid_from)
                        values (%s,%s,%s,%s,%s,%s,%s,'SAR',0,'SAR',0,'SAR',0,'SAR',0,'SAR',
                                %s,'SAR',%s,'landed-cost-v1',now())
                        """,
                        (
                            workspace.tenant_id,
                            line_id,
                            decision_id,
                            packs,
                            packs * size,
                            unit,
                            price,
                            packs * price,
                            Jsonb(
                                {
                                    "quantity": str(packs),
                                    "normalised_base_quantity": str(packs * size),
                                    "unit_price": {"amount": str(price), "currency": "SAR"},
                                }
                            ),
                        ),
                    )
                recipient_id, response_id = uuid4(), uuid4()
                cur.execute(
                    "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
                    "values (%s,%s,%s,%s,'sent')",
                    (recipient_id, workspace.tenant_id, rfq_id, supplier_id),
                )
                cur.execute(
                    "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
                    "values (%s,%s,%s,%s)",
                    (response_id, workspace.tenant_id, recipient_id, quotation_id),
                )
                responses.append(response_id)
        conn.commit()
    try:
        yield Round1Rfq(workspace, rfq_id, branch_id, products, suppliers, quotations, responses)
    finally:
        cleanup_workspace(workspace)
