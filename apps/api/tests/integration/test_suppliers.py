from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with catalogue migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_supplier_commercial_terms_store_explicit_currency(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "suppliers")
        act_as(cur, workspace)
        supplier_id = uuid4()
        cur.execute(
            "insert into supplier "
            "(id,tenant_id,name,payment_terms,lead_time_days,"
            "minimum_order_value_amount,minimum_order_value_currency,"
            "delivery_fee_amount,delivery_fee_currency,status) "
            "values (%s,%s,'Fresh Foods','Net 30',4,250,'GBP',12.5,'GBP','preferred') "
            "returning minimum_order_value_amount,minimum_order_value_currency,"
            "delivery_fee_amount,delivery_fee_currency,status",
            (supplier_id, workspace.tenant_id),
        )
        row = cur.fetchone()
        assert row == (Decimal("250.0000"), "GBP", Decimal("12.5000"), "GBP", "preferred")


def test_archiving_supplier_keeps_the_row(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "supplier-archive")
        act_as(cur, workspace)
        supplier_id = uuid4()
        cur.execute(
            "insert into supplier (id,tenant_id,name) values (%s,%s,'Old Supplier')",
            (supplier_id, workspace.tenant_id),
        )
        cur.execute(
            "update supplier set status = 'archived' where id = %s returning status",
            (supplier_id,),
        )
        assert cur.fetchone() == ("archived",)
        cur.execute("select id from supplier where id = %s", (supplier_id,))
        assert cur.fetchone() == (supplier_id,)


def test_deleting_a_referenced_supplier_nulls_the_preference_at_database_level(
    conn: object,
) -> None:
    """workspace_product.preferred_supplier_id is `on delete set null` (migration
    20260819000013) — a soft, advisory pointer, not a hard link. Refusing to remove a
    supplier still in use is a T020 APPLICATION-level rule (service.archive_supplier ->
    409 with archive_available, guarding archive rather than a raw delete): see
    _supplier_is_referenced in service.py. This test asserts the actual database
    guarantee; it does not exercise the 409 path, which needs router/service-level
    coverage this suite does not yet have.
    """
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "supplier-reference")
        act_as(cur, workspace)
        supplier_id = uuid4()
        cur.execute(
            "insert into supplier (id,tenant_id,name) values (%s,%s,'Referenced Supplier')",
            (supplier_id, workspace.tenant_id),
        )
        product_id = make_workspace_product(cur, workspace, name="Product", supplier_id=supplier_id)
        cur.execute("delete from supplier where id = %s", (supplier_id,))
        cur.execute(
            "select preferred_supplier_id from workspace_product where id = %s", (product_id,)
        )
        assert cur.fetchone() == (None,)
