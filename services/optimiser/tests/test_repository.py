from __future__ import annotations

import os
from uuid import uuid4

import pytest

from procurepilot_optimiser_worker.models import BasketItem, BasketJob

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize("rfq_filter", [False, True])
def test_read_current_offers_prices_only_rfq_reply_when_filtered(
    advanced: bool,
    rfq_filter: bool,
) -> None:
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
                "insert into supplier (id,tenant_id,name,status) values (%s,%s,'Supplier "
                "A','active')",
                (supplier_a_id, tenant_id),
            )
            cur.execute(
                "insert into supplier (id,tenant_id,name,status) values (%s,%s,'Supplier "
                "B','active')",
                (supplier_b_id, tenant_id),
            )
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,'Cooking Oil "
                "5L','litre')",
                (canonical_product_id,),
            )
            cur.execute(
                "insert into workspace_product "
                "(id,tenant_id,canonical_product_id,tenant_name,status) "
                "values (%s,%s,%s,'Cooking Oil','active')",
                (workspace_product_id, tenant_id, canonical_product_id),
            )
            cur.execute(
                "insert into document "
                "(id,tenant_id,storage_bucket,storage_path,mime_type,created_by) "
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
                "(id,tenant_id,quotation_line_id,candidate_workspace_product_id,confidence,"
                "reasons,rank,scoring_version) "
                "values (%s,%s,%s,%s,0.95,%s,1,'v1')",
                (match_candidate_id, tenant_id, quotation_line_id, workspace_product_id, Jsonb({})),
            )
            cur.execute(
                "insert into match_decision "
                "(id,tenant_id,quotation_line_id,matched_workspace_product_id,"
                "selected_match_candidate_id,"
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
                    %s, 'landed-cost-v1', now()
                )
                """,
                (landed_cost_id, tenant_id, quotation_line_id, match_decision_id, Jsonb({})),
            )
            # A re-cost of the same decision under v2 must replace v1 in the read model.
            cur.execute(
                "insert into landed_cost (tenant_id,quotation_line_id,match_decision_id,"
                "quantity,normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,"
                "vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,discount_amount,"
                "discount_currency,other_charges_currency,total_amount,total_currency,raw_inputs,"
                "rule_version,valid_from,recorded_at) "
                "select tenant_id,quotation_line_id,match_decision_id,quantity,"
                "normalised_base_quantity,"
                "base_unit,unit_price_amount,unit_price_currency,vat_amount,vat_currency,"
                "delivery_fee_amount,delivery_fee_currency,discount_amount,discount_currency,"
                "other_charges_currency,total_amount,total_currency,raw_inputs,'landed-cost-v2',"
                "valid_from,now()+interval '1 second' from landed_cost where id=%s",
                (landed_cost_id,),
            )
            # The older quotation was learned/re-costed later, so latest-price selects it.
            older_quote = uuid4()
            missing_product, missing_canonical = uuid4(), uuid4()
            cur.execute(
                "insert into canonical_product (id,name,base_unit) values (%s,'Other oil','litre')",
                (missing_canonical,),
            )
            cur.execute(
                "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                "values (%s,%s,%s,'Unquoted in reply')",
                (missing_product, tenant_id, missing_canonical),
            )
            cur.execute(
                "insert into quotation "
                "(id,tenant_id,document_id,supplier_id,currency,status,created_at) "
                "values (%s,%s,%s,%s,'GBP','reviewed',now()-interval '30 days')",
                (older_quote, tenant_id, document_id, supplier_a_id),
            )
            for product, number in ((workspace_product_id, 1), (missing_product, 2)):
                older_line, older_decision, older_cost = uuid4(), uuid4(), uuid4()
                cur.execute(
                    "insert into quotation_line "
                    "(id,tenant_id,quotation_id,line_number,original_text) "
                    "values (%s,%s,%s,%s,'Older cheap price')",
                    (older_line, tenant_id, older_quote, number),
                )
                cur.execute(
                    "insert into match_decision (id,tenant_id,quotation_line_id,"
                    "matched_workspace_product_id,outcome,is_automatic,confidence) "
                    "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                    (older_decision, tenant_id, older_line, product),
                )
                cur.execute(
                    """
                    insert into landed_cost (id,tenant_id,quotation_line_id,match_decision_id,
                      quantity,normalised_base_quantity,base_unit,unit_price_amount,unit_price_currency,
                      vat_amount,vat_currency,delivery_fee_amount,delivery_fee_currency,discount_amount,
                      discount_currency,other_charges_currency,total_amount,total_currency,raw_inputs,
                      rule_version,valid_from,recorded_at)
                    select %s,tenant_id,%s,%s,quantity,normalised_base_quantity,base_unit,20,'GBP',
                      0,'GBP',0,'GBP',0,'GBP','GBP',20,'GBP',raw_inputs,rule_version,valid_from,
                      now()+interval '1 minute' from landed_cost where id=%s
                    """,
                    (older_cost, older_line, older_decision, landed_cost_id),
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
            from psycopg.types.json import Jsonb

            from procurepilot_optimiser_worker.repository import (
                load_advanced_optimisation_input,
                load_job,
            )

            snapshot = (
                {
                    "rule_version": "advanced-basket-v1",
                    "rfq": {"price_quotation_ids": [str(quotation_id)]},
                }
                if rfq_filter
                else {"rule_version": "advanced-basket-v1"}
            )
            job = job.model_copy(
                update={
                    "items": [
                        *job.items,
                        BasketItem(workspace_product_id=missing_product, quantity="15.000000"),
                    ]
                }
            )
            conn.execute(
                "insert into basket_split_job (id,tenant_id,requested_by,supplier_ids,items,"
                "request_snapshot,status) values (%s,%s,%s,%s,%s,%s,'queued')",
                (
                    job.id,
                    tenant_id,
                    membership_id,
                    job.supplier_ids,
                    Jsonb([item.model_dump(mode="json") for item in job.items]),
                    Jsonb(snapshot),
                ),
            )
            if advanced:
                optimisation = load_advanced_optimisation_input(
                    conn, job_id=job.id, tenant_id=tenant_id
                )
                offers = optimisation.offers
                if rfq_filter:
                    from procurepilot_optimiser_worker.solver import solve_advanced_basket

                    result = solve_advanced_basket(input_payload=optimisation)
                    baseline = next(
                        b
                        for b in result.single_supplier_baselines
                        if b.supplier_id == supplier_a_id
                    )
                    assert not baseline.feasible
                    assert baseline.total_landed_cost is None
            else:
                offers = read_current_offers(
                    conn, job=load_job(conn, job_id=job.id, tenant_id=tenant_id)
                )

        offer = next(
            offer for offer in offers if offer.workspace_product_id == workspace_product_id
        )
        assert offer.workspace_product_id == workspace_product_id
        assert offer.supplier_id == supplier_a_id
        assert offer.quantity == "15.000000"
        assert offer.total_landed_cost.amount == ("30.0000" if rfq_filter else "10.0000")
        assert offer.total_landed_cost.currency == "GBP"
        assert len(offers) == (1 if rfq_filter else 2)
        assert any(o.workspace_product_id == missing_product for o in offers) is not rfq_filter
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


def test_read_current_offers_ignores_a_superseded_match_decision() -> None:
    """Spec 023 R5: a corrected match moves the line's price to the corrected product.

    The supplier's line was first matched to cooking oil (automatic), then corrected to sugar.
    A basket asking for cooking oil must no longer see that line's price.
    """
    psycopg = pytest.importorskip("psycopg")
    from psycopg.types.json import Jsonb

    from procurepilot_optimiser_worker.repository import read_current_offers

    tenant_id, user_id, membership_id, invitation_id = uuid4(), uuid4(), uuid4(), uuid4()
    supplier_id = uuid4()
    oil_id, sugar_id = uuid4(), uuid4()
    document_id, quotation_id, line_id = uuid4(), uuid4(), uuid4()
    oil_candidate, sugar_candidate = uuid4(), uuid4()
    first_decision, correction = uuid4(), uuid4()
    email = f"optimiser-supersede-{tenant_id.hex[:8]}@example.test"

    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            for statement in (
                "insert into supported_region (code,label_en,label_ar) "
                "values ('GB','UK','ب') on conflict do nothing",
                "insert into supported_currency (code,label_en,label_ar) "
                "values ('GBP','Pound','ج') on conflict do nothing",
                "insert into supported_tax_model (code,label_en,label_ar,region_code) "
                "values ('uk_vat','UK VAT','ض','GB') on conflict do nothing",
            ):
                cur.execute(statement)
            cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
            cur.execute(
                "insert into platform_invitation (id,email,token_hash,expires_at) "
                "values (%s,%s,%s, now() + interval '7 days')",
                (invitation_id, email, f"hash-{invitation_id}"),
            )
            cur.execute(
                "insert into tenant "
                "(id,name,slug,region,currency,tax_model,platform_invitation_id) "
                "values (%s,'Supersede','supersede','GB','GBP','uk_vat',%s)",
                (tenant_id, invitation_id),
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'owner',true)",
                (membership_id, tenant_id, user_id, email),
            )
            cur.execute(
                "insert into supplier (id,tenant_id,name,status) "
                "values (%s,%s,'Al Wafra','active')",
                (supplier_id, tenant_id),
            )
            for product_id, name in ((oil_id, "Cooking Oil"), (sugar_id, "Sugar")):
                canonical_id = uuid4()
                cur.execute(
                    "insert into canonical_product (id,name,base_unit) values (%s,%s,'kilogram')",
                    (canonical_id, f"{name} {tenant_id.hex[:6]}"),
                )
                cur.execute(
                    "insert into workspace_product "
                    "(id,tenant_id,canonical_product_id,tenant_name,status) "
                    "values (%s,%s,%s,%s,'active')",
                    (product_id, tenant_id, canonical_id, name),
                )
            cur.execute(
                "insert into document "
                "(id,tenant_id,storage_bucket,storage_path,mime_type,created_by) "
                "values (%s,%s,'quotations',%s,'application/pdf',%s)",
                (document_id, tenant_id, f"tenants/{tenant_id}/quotations/q.pdf", membership_id),
            )
            cur.execute(
                "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
                "values (%s,%s,%s,%s,'GBP','reviewed')",
                (quotation_id, tenant_id, document_id, supplier_id),
            )
            cur.execute(
                "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text) "
                "values (%s,%s,%s,1,'سكر 50 كجم')",
                (line_id, tenant_id, quotation_id),
            )
            for candidate_id, product_id, rank in (
                (oil_candidate, oil_id, 1),
                (sugar_candidate, sugar_id, 2),
            ):
                cur.execute(
                    "insert into match_candidate (id,tenant_id,quotation_line_id,"
                    "candidate_workspace_product_id,confidence,reasons,rank,scoring_version) "
                    "values (%s,%s,%s,%s,0.95,%s,%s,'v1')",
                    (candidate_id, tenant_id, line_id, product_id, Jsonb({}), rank),
                )
            cur.execute(
                "insert into match_decision (id,tenant_id,quotation_line_id,"
                "matched_workspace_product_id,selected_match_candidate_id,outcome,is_automatic,"
                "confidence) values (%s,%s,%s,%s,%s,'same_product',true,0.95)",
                (first_decision, tenant_id, line_id, oil_id, oil_candidate),
            )
            cur.execute(
                "insert into match_decision (id,tenant_id,quotation_line_id,"
                "matched_workspace_product_id,selected_match_candidate_id,outcome,is_automatic,"
                "decided_by,confidence,supersedes_decision_id) "
                "values (%s,%s,%s,%s,%s,'same_product',false,%s,0.95,%s)",
                (
                    correction,
                    tenant_id,
                    line_id,
                    sugar_id,
                    sugar_candidate,
                    membership_id,
                    first_decision,
                ),
            )
            for decision_id in (first_decision, correction):
                cur.execute(
                    """
                    insert into landed_cost (
                        tenant_id, quotation_line_id, match_decision_id,
                        quantity, normalised_base_quantity, base_unit,
                        unit_price_amount, unit_price_currency, vat_amount, vat_currency,
                        delivery_fee_amount, delivery_fee_currency, discount_amount,
                        discount_currency, other_charges_currency, total_amount, total_currency,
                        raw_inputs, rule_version, valid_from
                    ) values (%s, %s, %s, 1, 50, 'kilogram', 81, 'GBP', 0, 'GBP', 0, 'GBP',
                              0, 'GBP', 'GBP', 81, 'GBP', %s, 'landed-cost-v1', now())
                    """,
                    (tenant_id, line_id, decision_id, Jsonb({})),
                )

            def offers_for(product_id: object) -> list[object]:
                job = BasketJob(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    supplier_ids=[supplier_id, uuid4()],
                    items=[BasketItem(workspace_product_id=product_id, quantity="50.000000")],
                )
                return read_current_offers(conn, job=job)

            assert offers_for(oil_id) == []
            sugar_offers = offers_for(sugar_id)
            assert [offer.supplier_id for offer in sugar_offers] == [supplier_id]
        conn.rollback()
