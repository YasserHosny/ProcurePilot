from __future__ import annotations

import os
from uuid import uuid4

import pytest

from procurepilot_optimiser_worker.models import BasketItem, BasketJob

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_read_current_offers_projects_from_normalised_base_unit_not_pack_quantity() -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg.types.json import Jsonb

    from procurepilot_optimiser_worker.repository import read_current_offers

    database_url = os.environ["TEST_DATABASE_URL"]
    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    supplier_a_id, supplier_b_id = uuid4(), uuid4()
    canonical_product_id, workspace_product_id = uuid4(), uuid4()
    document_id, quotation_id, quotation_line_id = uuid4(), uuid4(), uuid4()
    match_decision_id, match_candidate_id, landed_cost_id = uuid4(), uuid4(), uuid4()
    email = f"optimiser-repo-{tenant_id.hex[:8]}@example.test"

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into supported_region (code,label_en,label_ar) "
                "values ('GB','UK','ب') on conflict do nothing"
            )
            cur.execute(
                "insert into supported_currency (code,label_en,label_ar) "
                "values ('GBP','Pound','ج') on conflict do nothing"
            )
            cur.execute(
                "insert into supported_tax_model (code,label_en,label_ar,region_code) "
                "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing"
            )
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
            cur.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at) "
                "values (%s,%s,%s, now() + interval '7 days')",
                (invitation_id, email, f"hash-{invitation_id}"),
            )
            cur.execute(
                "insert into tenant "
                "(id,name,slug,region,currency,tax_model,platform_invitation_id) "
                "values (%s,'Optimiser Repository','optimiser-repository','GB','GBP','uk_vat',%s)",
                (tenant_id, invitation_id),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (membership_id, tenant_id, user_id, email),
            )
            cur.execute(
                "insert into supplier (id,tenant_id,name,status) values (%s,%s,'Supplier A','active')",
                (supplier_a_id, tenant_id),
            )
            cur.execute(
                "insert into supplier (id,tenant_id,name,status) values (%s,%s,'Supplier B','active')",
                (supplier_b_id, tenant_id),
            )
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,'Cooking Oil 5L','litre')",
                (canonical_product_id,),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name,status) "
                "values (%s,%s,%s,'Cooking Oil','active')",
                (workspace_product_id, tenant_id, canonical_product_id),
            )
            cur.execute(
                "insert into document (id,tenant_id,storage_bucket,storage_path,mime_type,created_by) "
                "values (%s,%s,'quotations',%s,'application/pdf',%s)",
                (document_id, tenant_id, f"tenants/{tenant_id}/quotations/q.pdf", membership_id),
            )
            cur.execute(
                "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
                "values (%s,%s,%s,%s,'GBP','reviewed')",
                (quotation_id, tenant_id, document_id, supplier_a_id),
            )
            cur.execute(
                "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text) "
                "values (%s,%s,%s,1,'6 x 5L cooking oil case')",
                (quotation_line_id, tenant_id, quotation_id),
            )
            cur.execute(
                "insert into match_candidate "
                "(id,tenant_id,quotation_line_id,candidate_workspace_product_id,confidence,reasons,rank,scoring_version) "
                "values (%s,%s,%s,%s,0.95,%s,1,'v1')",
                (match_candidate_id, tenant_id, quotation_line_id, workspace_product_id, Jsonb({})),
            )
            cur.execute(
                "insert into match_decision "
                "(id,tenant_id,quotation_line_id,matched_workspace_product_id,selected_match_candidate_id,"
                "outcome,is_automatic,confidence) "
                "values (%s,%s,%s,%s,%s,'same_product',true,0.95)",
                (
                    match_decision_id,
                    tenant_id,
                    quotation_line_id,
                    workspace_product_id,
                    match_candidate_id,
                ),
            )
            # One case (quantity=1) of 6x5L = 30 litres normalised, £60.00 total —
            # a supplier offer priced per case, not per litre.
            cur.execute(
                """
                insert into landed_cost (
                    id, tenant_id, quotation_line_id, match_decision_id,
                    quantity, normalised_base_quantity, base_unit,
                    unit_price_amount, unit_price_currency,
                    vat_amount, vat_currency,
                    delivery_fee_amount, delivery_fee_currency,
                    discount_amount, discount_currency,
                    other_charges_currency,
                    total_amount, total_currency,
                    raw_inputs, rule_version, valid_from
                ) values (
                    %s, %s, %s, %s,
                    1, 30, 'litre',
                    60, 'GBP',
                    0, 'GBP',
                    0, 'GBP',
                    0, 'GBP',
                    'GBP',
                    60, 'GBP',
                    %s, 'v1', now()
                )
                """,
                (landed_cost_id, tenant_id, quotation_line_id, match_decision_id, Jsonb({})),
            )
        conn.commit()

    try:
        with psycopg.connect(database_url) as conn:
            # Requesting 15 litres — half of the 30-litre case — must project half the
            # case price, not half of a per-pack-count price (the bug: quantity=1 case).
            job = BasketJob(
                id=uuid4(),
                tenant_id=tenant_id,
                supplier_ids=[supplier_a_id, supplier_b_id],
                items=[BasketItem(workspace_product_id=workspace_product_id, quantity="15.000000")],
            )
            offers = read_current_offers(conn, job=job)

        assert len(offers) == 1
        offer = offers[0]
        assert offer.workspace_product_id == workspace_product_id
        assert offer.supplier_id == supplier_a_id
        assert offer.quantity == "15.000000"
        assert offer.total_landed_cost.amount == "30.0000"
        assert offer.total_landed_cost.currency == "GBP"
    finally:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                # The owner-guard trigger refuses to delete the last active owner's membership
                # row, even via cascade from a tenant delete.
                cur.execute("set session_replication_role = replica")
                try:
                    cur.execute("delete from tenant where id = %s", (tenant_id,))
                    cur.execute("delete from auth.users where id = %s", (user_id,))
                    cur.execute("delete from platform_invitation where id = %s", (invitation_id,))
                finally:
                    cur.execute("set session_replication_role = default")
            conn.commit()
