"""RFQ response comparison: landed cost at RFQ quantities, priced like the split (PPS-123)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from integration.test_rfq_service_e2e import _seed_tenant
from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.rfq.schemas import RfqResponseComparison, RfqResponseComparisonList
from procurepilot_api.modules.rfq.service import RfqService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs Postgres with the migrations applied",
)


def _member(tenant_id: UUID, user_id: UUID, membership_id: UUID) -> CurrentMember:
    return CurrentMember(
        membership_id=membership_id,
        tenant_id=tenant_id,
        user_id=user_id,
        email=f"rfq-landed-{uuid4().hex}@example.test",
        role=MemberRole.owner,
    )


def _make_document(
    cur: psycopg.Cursor, *, tenant_id: UUID, membership_id: UUID, doc_id: UUID
) -> None:
    cur.execute(
        "insert into document "
        "(id,tenant_id,storage_bucket,storage_path,mime_type,content_hash,created_by) "
        "values (%s,%s,'quotation-documents',%s,'application/pdf',%s,%s)",
        (
            doc_id,
            tenant_id,
            f"tenants/{tenant_id}/quotations/{doc_id}/quote.pdf",
            f"hash-{doc_id}",
            membership_id,
        ),
    )


def _insert_landed_cost(
    cur: psycopg.Cursor,
    *,
    tenant_id: UUID,
    quotation_line_id: UUID,
    match_decision_id: UUID,
    quantity: Decimal,
    normalised_base_quantity: Decimal,
    unit_price_amount: Decimal,
    total_amount: Decimal,
    currency: str = "GBP",
    rule_version: str = "landed-cost-v1",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    recorded_at: datetime | None = None,
    delivery_fee_amount: Decimal = Decimal("0"),
) -> UUID:
    landed_id = uuid4()
    now = datetime.now(UTC)
    cur.execute(
        """
        insert into landed_cost (
          id, tenant_id, quotation_line_id, match_decision_id, quantity,
          normalised_base_quantity, base_unit, unit_price_amount, unit_price_currency,
          vat_amount, vat_currency, delivery_fee_amount, delivery_fee_currency,
          discount_amount, discount_currency, other_charges_amount, other_charges_currency,
          total_amount, total_currency, raw_inputs, rule_version, valid_from, valid_to,
          recorded_at
        ) values (
          %s, %s, %s, %s, %s, %s, 'each', %s, %s,
          0, %s, %s, %s, 0, %s, 0, %s,
          %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            landed_id,
            tenant_id,
            quotation_line_id,
            match_decision_id,
            quantity,
            normalised_base_quantity,
            unit_price_amount,
            currency,
            currency,
            delivery_fee_amount,
            currency,
            currency,
            currency,
            total_amount,
            currency,
            Jsonb({"quantity": str(quantity), "total": str(total_amount)}),
            rule_version,
            valid_from or now - timedelta(days=1),
            valid_to,
            recorded_at or now,
        ),
    )
    return landed_id


def _seed_two_product_rfq(
    cur: psycopg.Cursor,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    rfq_qty_a: Decimal = Decimal("3"),
    rfq_qty_b: Decimal = Decimal("10"),
    pack_base_a: Decimal = Decimal("5"),
    pack_base_b: Decimal = Decimal("1"),
) -> dict[str, UUID]:
    """Two-product RFQ with two supplier replies; returns ids for further seeding."""
    rfq_id, branch_id = uuid4(), uuid4()
    supp1_id, supp2_id = uuid4(), uuid4()
    prod_a, prod_b = uuid4(), uuid4()
    can_a, can_b = uuid4(), uuid4()
    cur.execute(
        "insert into branch (id, tenant_id, name) values (%s, %s, %s)",
        (branch_id, tenant_id, "Main"),
    )
    cur.execute(
        "insert into canonical_product (id,name,base_unit) values (%s,%s,'each'), (%s,%s,'each')",
        (can_a, f"can-a-{can_a.hex[:6]}", can_b, f"can-b-{can_b.hex[:6]}"),
    )
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s), (%s,%s,%s,%s)",
        (prod_a, tenant_id, can_a, "ProdA", prod_b, tenant_id, can_b, "ProdB"),
    )
    cur.execute(
        "insert into pack_definition (id,tenant_id,workspace_product_id,pack_count,unit_size) "
        "values (%s,%s,%s,1,%s), (%s,%s,%s,1,%s)",
        (uuid4(), tenant_id, prod_a, pack_base_a, uuid4(), tenant_id, prod_b, pack_base_b),
    )
    cur.execute(
        "insert into supplier (id,tenant_id,name,contact_email) values "
        "(%s,%s,%s,%s), (%s,%s,%s,%s)",
        (
            supp1_id,
            tenant_id,
            "Supplier 1",
            "s1@example.test",
            supp2_id,
            tenant_id,
            "Supplier 2",
            "s2@example.test",
        ),
    )
    cur.execute(
        "insert into rfq "
        "(id,tenant_id,created_by_membership_id,status,needed_by_date,idempotency_key) "
        "values (%s,%s,%s,'responded',%s,%s)",
        (rfq_id, tenant_id, membership_id, date.today(), uuid4()),
    )
    cur.execute(
        "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity,position) "
        "values (%s,%s,%s,%s,%s,1), (%s,%s,%s,%s,%s,2)",
        (
            uuid4(),
            tenant_id,
            rfq_id,
            prod_a,
            rfq_qty_a,
            uuid4(),
            tenant_id,
            rfq_id,
            prod_b,
            rfq_qty_b,
        ),
    )
    rec1_id, rec2_id = uuid4(), uuid4()
    cur.execute(
        "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) values "
        "(%s,%s,%s,%s,'sent'), (%s,%s,%s,%s,'sent')",
        (rec1_id, tenant_id, rfq_id, supp1_id, rec2_id, tenant_id, rfq_id, supp2_id),
    )

    def _reply(
        *,
        supplier_id: UUID,
        recipient_id: UUID,
        line_specs: list[tuple[UUID | None, Decimal, Decimal, str]],
    ) -> tuple[UUID, UUID, dict[UUID, tuple[UUID, UUID]]]:
        """line_specs: (product_or_none, quoted_qty, unit_price, original_text)."""
        doc_id, quot_id, resp_id = uuid4(), uuid4(), uuid4()
        _make_document(cur, tenant_id=tenant_id, membership_id=membership_id, doc_id=doc_id)
        cur.execute(
            "insert into quotation (id,tenant_id,document_id,supplier_id,currency,status) "
            "values (%s,%s,%s,%s,'GBP','reviewed')",
            (quot_id, tenant_id, doc_id, supplier_id),
        )
        lines: dict[UUID, tuple[UUID, UUID]] = {}
        for number, (product_id, qty, price, text) in enumerate(line_specs, start=1):
            ql_id = uuid4()
            cur.execute(
                "insert into quotation_line "
                "(id,tenant_id,quotation_id,line_number,original_text,quantity,"
                "unit_price_amount,unit_price_currency) "
                "values (%s,%s,%s,%s,%s,%s,%s,'GBP')",
                (ql_id, tenant_id, quot_id, number, text, qty, price),
            )
            if product_id is None:
                continue
            md_id = uuid4()
            cur.execute(
                "insert into match_decision "
                "(id,tenant_id,quotation_line_id,matched_workspace_product_id,outcome,"
                "is_automatic,confidence) "
                "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                (md_id, tenant_id, ql_id, product_id),
            )
            lines[product_id] = (ql_id, md_id)
        cur.execute(
            "insert into rfq_response (id,tenant_id,rfq_recipient_id,quotation_id) "
            "values (%s,%s,%s,%s)",
            (resp_id, tenant_id, recipient_id, quot_id),
        )
        return resp_id, quot_id, lines

    # Reply 1: quotes A at qty 1 (≠ RFQ 3) and B at RFQ qty.
    resp1_id, quot1_id, lines1 = _reply(
        supplier_id=supp1_id,
        recipient_id=rec1_id,
        line_specs=[
            (prod_a, Decimal("1"), Decimal("10"), "a"),
            (prod_b, Decimal("10"), Decimal("2"), "b"),
        ],
    )
    # Reply 2: both matched at RFQ quantities.
    resp2_id, quot2_id, lines2 = _reply(
        supplier_id=supp2_id,
        recipient_id=rec2_id,
        line_specs=[
            (prod_a, Decimal("3"), Decimal("9"), "a"),
            (prod_b, Decimal("10"), Decimal("2.5"), "b"),
        ],
    )
    return {
        "rfq_id": rfq_id,
        "prod_a": prod_a,
        "prod_b": prod_b,
        "supp1_id": supp1_id,
        "supp2_id": supp2_id,
        "resp1_id": resp1_id,
        "resp2_id": resp2_id,
        "quot1_id": quot1_id,
        "quot2_id": quot2_id,
        "ql1_a": lines1[prod_a][0],
        "md1_a": lines1[prod_a][1],
        "ql1_b": lines1[prod_b][0],
        "md1_b": lines1[prod_b][1],
        "ql2_a": lines2[prod_a][0],
        "md2_a": lines2[prod_a][1],
        "ql2_b": lines2[prod_b][0],
        "md2_b": lines2[prod_b][1],
    }


def _four_landed_costs(
    ids: dict[str, UUID],
) -> list[tuple[UUID, UUID, Decimal, Decimal, Decimal, Decimal]]:
    """(line, decision, quantity, normalised base quantity, unit price, total) for both replies."""
    d = Decimal
    return [
        (ids["ql1_a"], ids["md1_a"], d("1"), d("10"), d("10"), d("100")),
        (ids["ql1_b"], ids["md1_b"], d("10"), d("10"), d("2"), d("20")),
        (ids["ql2_a"], ids["md2_a"], d("3"), d("15"), d("9"), d("27")),
        (ids["ql2_b"], ids["md2_b"], d("10"), d("10"), d("2.5"), d("25")),
    ]


def _by_response(result: RfqResponseComparisonList) -> dict[UUID, RfqResponseComparison]:
    return {item.id: item for item in result.items}


def _costs_by_product(item: RfqResponseComparison) -> dict[UUID, Decimal]:
    return {c.workspace_product_id: c.total_amount for c in item.rfq_landed_costs}


def test_rfq_landed_cost_uses_rfq_quantity_not_quoted_quantity() -> None:
    """landed 100 / base 10 × (RFQ 3 packs × pack base 5) → 150.0000."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("reset role")
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"lc-qty-{uuid4().hex[:8]}"
            )
            ids = _seed_two_product_rfq(cur, tenant_id=tenant_id, membership_id=membership_id)
            # Reply 1 product A: unit rate 10; RFQ basket = 15 base units → 150.
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_a"],
                match_decision_id=ids["md1_a"],
                quantity=Decimal("1"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("10"),
                total_amount=Decimal("100"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_b"],
                match_decision_id=ids["md1_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2"),
                total_amount=Decimal("20"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql2_a"],
                match_decision_id=ids["md2_a"],
                quantity=Decimal("3"),
                normalised_base_quantity=Decimal("15"),
                unit_price_amount=Decimal("9"),
                total_amount=Decimal("27"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql2_b"],
                match_decision_id=ids["md2_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2.5"),
                total_amount=Decimal("25"),
            )
        conn.commit()

    result = RfqService(get_settings()).list_responses(
        member=_member(tenant_id, user_id, membership_id), rfq_id=ids["rfq_id"]
    )
    by_id = _by_response(result)
    resp1_costs = _costs_by_product(by_id[ids["resp1_id"]])
    assert resp1_costs[ids["prod_a"]] == Decimal("150.0000")
    assert resp1_costs[ids["prod_b"]] == Decimal("20.0000")
    resp2_costs = _costs_by_product(by_id[ids["resp2_id"]])
    assert resp2_costs[ids["prod_a"]] == Decimal("27.0000")
    assert resp2_costs[ids["prod_b"]] == Decimal("25.0000")
    for item in result.items:
        for cost in item.rfq_landed_costs:
            assert cost.total_currency == "GBP"


def test_rfq_landed_cost_keeps_delivery_in_total_not_qty_times_price() -> None:
    """When total_amount includes a delivery charge, scale that total — not qty × unit price."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("reset role")
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"lc-deliv-{uuid4().hex[:8]}"
            )
            ids = _seed_two_product_rfq(
                cur,
                tenant_id=tenant_id,
                membership_id=membership_id,
                rfq_qty_a=Decimal("2"),
                pack_base_a=Decimal("5"),
            )
            # Quoted 2 packs × £5 = £10 merchandise; total_amount £16 includes £6 delivery.
            # RFQ basket = 2 × 5 = 10 base → projected 16.0000 (not 10.0000).
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_a"],
                match_decision_id=ids["md1_a"],
                quantity=Decimal("2"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("5"),
                total_amount=Decimal("16"),
                delivery_fee_amount=Decimal("6"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_b"],
                match_decision_id=ids["md1_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2"),
                total_amount=Decimal("20"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql2_a"],
                match_decision_id=ids["md2_a"],
                quantity=Decimal("2"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("5"),
                total_amount=Decimal("10"),
            )
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql2_b"],
                match_decision_id=ids["md2_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2"),
                total_amount=Decimal("20"),
            )
        conn.commit()

    result = RfqService(get_settings()).list_responses(
        member=_member(tenant_id, user_id, membership_id), rfq_id=ids["rfq_id"]
    )
    costs = _costs_by_product(_by_response(result)[ids["resp1_id"]])
    assert costs[ids["prod_a"]] == Decimal("16.0000")
    assert costs[ids["prod_a"]] != Decimal("10.0000")


def test_expired_landed_cost_and_unmatched_line_omit_entries() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("reset role")
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"lc-omit-{uuid4().hex[:8]}"
            )
            ids = _seed_two_product_rfq(cur, tenant_id=tenant_id, membership_id=membership_id)
            past = datetime.now(UTC) - timedelta(days=7)
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_a"],
                match_decision_id=ids["md1_a"],
                quantity=Decimal("1"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("10"),
                total_amount=Decimal("100"),
                valid_from=past - timedelta(days=30),
                valid_to=past,
            )
            # Product B on reply 1: valid cost.
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql1_b"],
                match_decision_id=ids["md1_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2"),
                total_amount=Decimal("20"),
            )
            # Reply 2 product A: drop the match so the line is pending.
            cur.execute("delete from match_decision where id = %s", (ids["md2_a"],))
            _insert_landed_cost(
                cur,
                tenant_id=tenant_id,
                quotation_line_id=ids["ql2_b"],
                match_decision_id=ids["md2_b"],
                quantity=Decimal("10"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("2.5"),
                total_amount=Decimal("25"),
            )
        conn.commit()

    result = RfqService(get_settings()).list_responses(
        member=_member(tenant_id, user_id, membership_id), rfq_id=ids["rfq_id"]
    )
    by_id = _by_response(result)
    assert ids["prod_a"] not in _costs_by_product(by_id[ids["resp1_id"]])
    assert _costs_by_product(by_id[ids["resp1_id"]])[ids["prod_b"]] == Decimal("20.0000")
    assert ids["prod_a"] not in _costs_by_product(by_id[ids["resp2_id"]])
    assert _costs_by_product(by_id[ids["resp2_id"]])[ids["prod_b"]] == Decimal("25.0000")
    resp2 = by_id[ids["resp2_id"]]
    assert any(line.pending_match for line in resp2.lines)


def test_supplier_terms_apply_delivery_fee_and_expired() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("reset role")
            tenant_id, user_id, membership_id = _seed_tenant(
                cur, email_suffix=f"lc-terms-{uuid4().hex[:8]}"
            )
            ids = _seed_two_product_rfq(cur, tenant_id=tenant_id, membership_id=membership_id)
            for ql, md, qty, base, price, total in _four_landed_costs(ids):
                _insert_landed_cost(
                    cur,
                    tenant_id=tenant_id,
                    quotation_line_id=ql,
                    match_decision_id=md,
                    quantity=qty,
                    normalised_base_quantity=base,
                    unit_price_amount=price,
                    total_amount=total,
                )
            # Supplier 1: in-force delivery fee.
            cur.execute(
                "insert into supplier_commercial_term "
                "(tenant_id,supplier_id,delivery_fee_amount,delivery_fee_currency,"
                "created_by_membership_id) values (%s,%s,12.5,'GBP',%s)",
                (tenant_id, ids["supp1_id"], membership_id),
            )
            # Supplier 2: a delivery fee that has expired, and a term in force with no fee,
            # minimum order or tiers. Neither changes what the split pays.
            past = datetime.now(UTC) - timedelta(days=3)
            cur.execute(
                "insert into supplier_commercial_term "
                "(tenant_id,supplier_id,delivery_fee_amount,delivery_fee_currency,"
                "effective_from,effective_to,created_by_membership_id) "
                "values (%s,%s,9,'GBP',%s,%s,%s)",
                (
                    tenant_id,
                    ids["supp2_id"],
                    past - timedelta(days=30),
                    past,
                    membership_id,
                ),
            )
            cur.execute(
                "insert into supplier_commercial_term "
                "(tenant_id,supplier_id,effective_from,created_by_membership_id) "
                "values (%s,%s,%s,%s)",
                (tenant_id, ids["supp2_id"], past, membership_id),
            )
        conn.commit()

    result = RfqService(get_settings()).list_responses(
        member=_member(tenant_id, user_id, membership_id), rfq_id=ids["rfq_id"]
    )
    by_id = _by_response(result)
    assert by_id[ids["resp1_id"]].supplier_terms_apply is True
    assert by_id[ids["resp2_id"]].supplier_terms_apply is False


def test_cross_tenant_landed_cost_and_terms_never_appear() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("reset role")
            tenant_a, user_a, mem_a = _seed_tenant(cur, email_suffix=f"lc-xa-{uuid4().hex[:8]}")
            ids_a = _seed_two_product_rfq(cur, tenant_id=tenant_a, membership_id=mem_a)
            for ql, md, qty, base, price, total in _four_landed_costs(ids_a):
                _insert_landed_cost(
                    cur,
                    tenant_id=tenant_a,
                    quotation_line_id=ql,
                    match_decision_id=md,
                    quantity=qty,
                    normalised_base_quantity=base,
                    unit_price_amount=price,
                    total_amount=total,
                )
            # Tenant A has no commercial terms → both false.
            tenant_b, _user_b, mem_b = _seed_tenant(cur, email_suffix=f"lc-xb-{uuid4().hex[:8]}")
            ids_b = _seed_two_product_rfq(cur, tenant_id=tenant_b, membership_id=mem_b)
            _insert_landed_cost(
                cur,
                tenant_id=tenant_b,
                quotation_line_id=ids_b["ql1_a"],
                match_decision_id=ids_b["md1_a"],
                quantity=Decimal("1"),
                normalised_base_quantity=Decimal("10"),
                unit_price_amount=Decimal("1"),
                total_amount=Decimal("9999"),
            )
            cur.execute(
                "insert into supplier_commercial_term "
                "(tenant_id,supplier_id,delivery_fee_amount,delivery_fee_currency,"
                "created_by_membership_id) values (%s,%s,500,'GBP',%s)",
                (tenant_b, ids_b["supp1_id"], mem_b),
            )
        conn.commit()

    result = RfqService(get_settings()).list_responses(
        member=_member(tenant_a, user_a, mem_a), rfq_id=ids_a["rfq_id"]
    )
    by_id = _by_response(result)
    assert all(item.supplier_terms_apply is False for item in result.items)
    for item in result.items:
        amounts = {c.total_amount for c in item.rfq_landed_costs}
        assert Decimal("9999.0000") not in amounts
        assert Decimal("9999") not in amounts
    assert _costs_by_product(by_id[ids_a["resp1_id"]])[ids_a["prod_a"]] == Decimal("150.0000")
