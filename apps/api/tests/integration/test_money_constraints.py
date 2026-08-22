from __future__ import annotations

from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    psycopg,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with catalogue migrations applied",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_minimum_order_amount_without_currency_is_rejected_by_database(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "money-minimum")
        act_as(cur, workspace)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into supplier "
                "(id,tenant_id,name,minimum_order_value_amount,minimum_order_value_currency) "
                "values (%s,%s,'Bad Money',100,null)",
                (uuid4(), workspace.tenant_id),
            )


def test_delivery_fee_amount_without_currency_is_rejected_by_database(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "money-delivery")
        act_as(cur, workspace)
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "insert into supplier "
                "(id,tenant_id,name,delivery_fee_amount,delivery_fee_currency) "
                "values (%s,%s,'Bad Delivery',10,null)",
                (uuid4(), workspace.tenant_id),
            )
