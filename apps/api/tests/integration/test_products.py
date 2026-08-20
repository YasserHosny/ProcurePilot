from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_canonical_product,
    make_workspace,
    make_workspace_product,
    psycopg,
    reset_role,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with catalogue migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_product_pack_base_quantity_is_generated_and_updates(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "products")
        canonical_id = make_canonical_product(cur, "olive oil")
        act_as(cur, workspace)
        product_id = uuid4()
        cur.execute(
            "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
            "values (%s,%s,%s,'Olive oil')",
            (product_id, workspace.tenant_id, canonical_id),
        )
        cur.execute(
            "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
            "values (%s,%s,6,5) returning base_quantity",
            (workspace.tenant_id, product_id),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == Decimal("30.000000")

        cur.execute(
            "update pack_definition set pack_count = 3, unit_size = 0.33 "
            "where workspace_product_id = %s returning base_quantity",
            (product_id,),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == Decimal("0.990000")


def test_base_quantity_cannot_be_written(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "generated")
        product_id = make_workspace_product(cur, workspace, name="Milk")
        with pytest.raises(psycopg.errors.GeneratedAlways):
            cur.execute(
                "insert into pack_definition "
                "(tenant_id,workspace_product_id,pack_count,unit_size,base_quantity) "
                "values (%s,%s,1,1,1)",
                (workspace.tenant_id, product_id),
            )


def test_cross_workspace_product_reads_return_not_found_shape(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "alpha-products")
        beta = make_workspace(cur, "beta-products")
        beta_product_id = make_workspace_product(cur, beta, name="Private product")
        reset_role(cur)
        act_as(cur, alpha)
        cur.execute("select id from workspace_product where id = %s", (beta_product_id,))
        assert cur.fetchall() == []


def test_archiving_product_keeps_the_row_resolvable(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "archive-products")
        product_id = make_workspace_product(cur, workspace, name="Old product")
        cur.execute(
            "update workspace_product set status = 'archived' where id = %s returning status",
            (product_id,),
        )
        row = cur.fetchone()
        assert row is not None and row[0] == "archived"
        cur.execute("select id from workspace_product where id = %s", (product_id,))
        assert cur.fetchone() == (product_id,)


def test_approved_substitute_is_private_to_workspace(conn: object) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "alpha-substitute")
        beta = make_workspace(cur, "beta-substitute")
        first = make_workspace_product(cur, alpha, name="First")
        second = make_workspace_product(cur, alpha, name="Second")
        reset_role(cur)
        act_as(cur, alpha)
        cur.execute(
            "insert into product_substitute "
            "(tenant_id,workspace_product_id,substitute_product_id) values (%s,%s,%s)",
            (alpha.tenant_id, first, second),
        )
        cur.execute("select substitute_product_id from product_substitute")
        assert cur.fetchall() == [(second,)]
        reset_role(cur)
        act_as(cur, beta)
        cur.execute("select substitute_product_id from product_substitute")
        assert cur.fetchall() == []
