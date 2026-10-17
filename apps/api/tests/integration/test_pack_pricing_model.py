"""Regression: request estimates are PER PACK (the purchasing unit), never per base unit.

Reproduces the 2026-10-17 demo defect with the real numbers: quantities are in packs (tins,
sacks, cartons), landed_cost rows carry quantity in packs plus a normalised base quantity, and
the estimate used at create/update/submit must (a) multiply cleanly with pack quantities and
(b) follow the RFQ response the request was prepared from rather than another supplier.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.test_rfq_service_e2e import _seed_tenant
from procurepilot_api.config import get_settings
from procurepilot_api.modules.requests.service import RequestsService, _compute_totals
from procurepilot_api.modules.requests.valuation import LineEstimate

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

# name, base_unit, base quantity per pack, request qty (packs), النور / الأمانة price per pack,
# الأمانة delivery fee
LINES = [
    ("oil tin 18L", "litre", Decimal(18), Decimal(10), Decimal(1680), Decimal(1725), Decimal(0)),
    (
        "rice sack 25kg",
        "kilogram",
        Decimal(25),
        Decimal(20),
        Decimal(940),
        Decimal(925),
        Decimal(0),
    ),
    ("sugar 25kg", "kilogram", Decimal(25), Decimal(10), Decimal(905), Decimal(890), Decimal(0)),
    (
        "pasta carton 20kg",
        "kilogram",
        Decimal(20),
        Decimal(15),
        Decimal(545),
        Decimal(575),
        Decimal(0),
    ),
    ("lentils kg", "kilogram", Decimal(1), Decimal(50), Decimal(72), Decimal(68), Decimal(250)),
]
NOOR_TOTAL = Decimal("56425")


def _seed(
    cur: psycopg.Cursor, tenant_id: UUID, membership_id: UUID
) -> tuple[list[UUID], dict[str, UUID]]:
    products: list[UUID] = []
    suppliers = {"noor": uuid4(), "amana": uuid4()}
    for key, sid in suppliers.items():
        cur.execute(
            "insert into supplier (id,tenant_id,name,contact_email) values (%s,%s,%s,%s)",
            (sid, tenant_id, key, f"{key}@example.com"),
        )
    rfq_id = uuid4()
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) values (%s,%s,%s,'responded',%s,%s)",
        (rfq_id, tenant_id, membership_id, date.today(), uuid4()),
    )
    quotations: dict[str, UUID] = {}
    responses: dict[str, UUID] = {}
    for key, sid in suppliers.items():
        doc_id, quot_id, rec_id, resp_id = uuid4(), uuid4(), uuid4(), uuid4()
        cur.execute(
            "insert into document (id,tenant_id,storage_bucket,storage_path,mime_type,"
            "content_hash,created_by) "
            "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
            (
                doc_id,
                tenant_id,
                f"tenants/{tenant_id}/quotations/{doc_id}/q.pdf",
                f"hash-{doc_id}",
                membership_id,
            ),
        )
        cur.execute(
            "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
            "values (%s,%s,%s,%s,'EGP','reviewed')",
            (quot_id, tenant_id, doc_id, sid),
        )
        cur.execute(
            "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,%s,'sent')",
            (rec_id, tenant_id, rfq_id, sid),
        )
        cur.execute(
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)",
            (resp_id, tenant_id, rec_id, quot_id),
        )
        quotations[key] = quot_id
        responses[key] = resp_id

    for n, (name, base_unit, base_qty, qty, noor, amana, amana_fee) in enumerate(LINES, start=1):
        canonical = uuid4()
        cur.execute(
            "insert into canonical_product (id,name,base_unit) values (%s,%s,%s)",
            (canonical, name, base_unit),
        )
        pid = uuid4()
        products.append(pid)
        cur.execute(
            "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
            "values (%s,%s,%s,%s)",
            (pid, tenant_id, canonical, name),
        )
        cur.execute(
            "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
            "values (%s,%s,1,%s)",
            (tenant_id, pid, base_qty),
        )
        cur.execute(
            "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) "
            "values (%s,%s,%s,%s,%s)",
            (uuid4(), tenant_id, rfq_id, pid, qty),
        )
        for key, price, fee in (("noor", noor, Decimal(0)), ("amana", amana, amana_fee)):
            ql, md = uuid4(), uuid4()
            cur.execute(
                "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text,"
                "quantity,unit_price_amount,unit_price_currency) "
                "values (%s,%s,%s,%s,%s,%s,%s,'EGP')",
                (ql, tenant_id, quotations[key], n, name, qty, price),
            )
            cur.execute(
                "insert into match_decision (id,tenant_id,quotation_line_id,"
                "matched_workspace_product_id,outcome,is_automatic,confidence) "
                "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                (md, tenant_id, ql, pid),
            )
            total = price * qty + fee
            cur.execute(
                "insert into landed_cost (id,tenant_id,quotation_line_id,match_decision_id,"
                "quantity,normalised_base_quantity,base_unit,unit_price_amount,"
                "unit_price_currency,vat_amount,vat_currency,delivery_fee_amount,"
                "delivery_fee_currency,discount_amount,discount_currency,other_charges_amount,"
                "other_charges_currency,total_amount,total_currency,raw_inputs,rule_version,"
                "valid_from,recorded_at) values (%s,%s,%s,%s,%s,%s,%s,%s,'EGP',0,'EGP',%s,'EGP',"
                "0,'EGP',0,'EGP',%s,'EGP','{}'::jsonb,'landed-cost-v1',now()-interval '1 day',"
                "now() + (%s || ' seconds')::interval)",
                (
                    uuid4(),
                    tenant_id,
                    ql,
                    md,
                    qty,
                    qty * base_qty,
                    base_unit,
                    price,
                    fee,
                    total,
                    "2" if key == "amana" else "1",
                ),  # الأمانة is the LATEST landed cost
            )
    return products, responses


def _request_row(
    cur: psycopg.Cursor, tenant_id: UUID, membership_id: UUID, resp: UUID | None
) -> UUID:
    branch, rid = uuid4(), uuid4()
    cur.execute("insert into branch (id,tenant_id,name) values (%s,%s,'Main')", (branch, tenant_id))
    cur.execute(
        "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
        "required_by_date,status,source_rfq_response_id) values (%s,%s,%s,%s,%s,'draft',%s)",
        (rid, tenant_id, branch, membership_id, date.today(), resp),
    )
    return rid


def _total(
    products: list[UUID], estimates: list[LineEstimate]
) -> tuple[Decimal | None, str | None, bool]:
    return _compute_totals([str(line[3]) for line in LINES], estimates)


def test_estimate_follows_source_response_and_is_per_pack() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, _user, membership_id = _seed_tenant(
                cur, email_suffix=f"packs-{uuid4().hex[:8]}"
            )
            products, responses = _seed(cur, tenant_id, membership_id)
            rid = _request_row(cur, tenant_id, membership_id, responses["noor"])
        conn.commit()

    service = RequestsService(settings=get_settings())
    estimates = service._estimate_products(products, request_id=rid)

    # Per-pack prices of the SOURCE response (النور), not الأمانة's, not per litre/kg.
    assert [e.unit_price_amount for e in estimates] == [
        Decimal(1680),
        Decimal(940),
        Decimal(905),
        Decimal(545),
        Decimal(72),
    ]
    total, currency, incomplete = _total(products, estimates)
    assert (total, currency, incomplete) == (NOOR_TOTAL, "EGP", False)


def test_estimate_without_source_response_is_still_per_pack() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, _user, membership_id = _seed_tenant(
                cur, email_suffix=f"packs-nosrc-{uuid4().hex[:8]}"
            )
            products, _ = _seed(cur, tenant_id, membership_id)
        conn.commit()

    estimates = RequestsService(settings=get_settings())._estimate_products(products)
    # Latest landed cost (الأمانة, incl. delivery) priced per PACK: 1725, 925, 890, 575, 73.
    assert [e.unit_price_amount for e in estimates] == [
        Decimal(1725),
        Decimal(925),
        Decimal(890),
        Decimal(575),
        Decimal(73),
    ]
    total, _currency, _ = _total(products, estimates)
    assert total == Decimal("56925")  # 56,675 quote lines + 250 delivery: not ~6,135
