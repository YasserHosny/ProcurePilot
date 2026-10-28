"""rfq_lines_for_quotation: what an RFQ asked for, seen from one of its replies (spec 023 R2)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

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
    make_quotation,
    make_supplier,
)
from procurepilot_api.modules.rfq.read_api import rfq_lines_for_quotation_with_conn

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


def _member_scope(cur: psycopg.Cursor, ws: Workspace) -> None:
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {
                    "sub": str(ws.user_id),
                    "tenant_id": str(ws.tenant_id),
                    "role": "authenticated",
                    "member_role": ws.role,
                }
            ),
        ),
    )


def _rfq_with_reply(
    cur: psycopg.Cursor, ws: Workspace, products: list[tuple[UUID, str]]
) -> tuple[UUID, UUID]:
    supplier_id = make_supplier(cur, ws, name="Al Dahabi")
    quotation_id = make_quotation(cur, ws, supplier_id=supplier_id, status="reviewed")
    rfq_id, recipient_id = uuid4(), uuid4()
    act_as(cur, ws)
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) values (%s,%s,%s,'responded',current_date + 7,%s)",
        (rfq_id, ws.tenant_id, ws.membership_id, uuid4()),
    )
    # Inserted out of position order on purpose: the read must order by position.
    for position, (product_id, quantity) in reversed(list(enumerate(products, start=1))):
        cur.execute(
            "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity,position) "
            "values (%s,%s,%s,%s,%s)",
            (ws.tenant_id, rfq_id, product_id, quantity, position),
        )
    cur.execute(
        "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
        "values (%s,%s,%s,%s,'sent')",
        (recipient_id, ws.tenant_id, rfq_id, supplier_id),
    )
    # Responses are captured by email ingestion (service role); members may only read them.
    reset_role(cur)
    cur.execute(
        "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) values (%s,%s,%s)",
        (ws.tenant_id, recipient_id, quotation_id),
    )
    return rfq_id, quotation_id


def test_reply_sees_its_rfq_lines_in_position_order_with_packs_and_aliases(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-read")
        rice = make_workspace_product(cur, ws, name="أرز بسمتي")
        flour = make_workspace_product(cur, ws, name="دقيق فاخر")
        act_as(cur, ws)
        # Newest pack wins (the requests module's rule): flour's purchasing pack is 1 × 10.
        cur.execute(
            "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size,"
            "created_at) values (%s,%s,1,10,now() + interval '1 second')",
            (ws.tenant_id, flour),
        )
        cur.execute(
            "insert into product_alias (tenant_id,workspace_product_id,alias_text,created_by) "
            "values (%s,%s,'دقيق',%s)",
            (ws.tenant_id, flour, ws.membership_id),
        )
        rfq_id, quotation_id = _rfq_with_reply(cur, ws, [(rice, "25"), (flour, "8")])
        reset_role(cur)

        _member_scope(cur, ws)
        context = rfq_lines_for_quotation_with_conn(conn, quotation_id)

    assert context is not None
    assert context.rfq_id == rfq_id
    assert [line.position for line in context.lines] == [1, 2]
    rice_line, flour_line = context.lines
    assert rice_line.workspace_product_id == rice
    assert rice_line.product_name == "أرز بسمتي"
    assert rice_line.quantity == Decimal("25")
    assert rice_line.pack_base_quantity == Decimal("30")  # helper pack: 6 × 5
    assert flour_line.pack_base_quantity == Decimal("10")
    assert flour_line.aliases == ("دقيق",)
    assert rice_line.aliases == ()


def test_a_quotation_that_answers_no_rfq_has_no_context(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-read-none")
        quotation_id = make_quotation(cur, ws, status="reviewed")
        reset_role(cur)
        _member_scope(cur, ws)
        assert rfq_lines_for_quotation_with_conn(conn, quotation_id) is None


def test_another_tenants_rfq_is_never_read(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        owner = make_workspace(cur, "rfq-read-owner")
        rice = make_workspace_product(cur, owner, name="Rice")
        _, quotation_id = _rfq_with_reply(cur, owner, [(rice, "5")])
        reset_role(cur)
        stranger = make_workspace(cur, "rfq-read-stranger")
        reset_role(cur)
        _member_scope(cur, stranger)
        assert rfq_lines_for_quotation_with_conn(conn, quotation_id) is None
