from __future__ import annotations

from uuid import uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
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


def test_alias_resolves_only_in_the_workspace_that_recorded_it(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "alpha-alias")
        beta = make_workspace(cur, "beta-alias")
        product_id = make_workspace_product(cur, alpha, name="Tomatoes")
        reset_role(cur)
        act_as(cur, alpha)
        alias_id = uuid4()
        cur.execute(
            "insert into product_alias "
            "(id,tenant_id,workspace_product_id,alias_text,created_by) "
            "values (%s,%s,%s,'supplier tomato case',%s)",
            (alias_id, alpha.tenant_id, product_id, alpha.membership_id),
        )
        cur.execute(
            "select workspace_product_id from product_alias "
            "where lower(alias_text) = lower('supplier tomato case')"
        )
        assert cur.fetchall() == [(product_id,)]

        reset_role(cur)
        act_as(cur, beta)
        cur.execute(
            "select workspace_product_id from product_alias "
            "where lower(alias_text) = lower('supplier tomato case')"
        )
        assert cur.fetchall() == []


def test_alias_wording_is_unique_per_workspace(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "alias-unique")
        product_id = make_workspace_product(cur, workspace, name="Water")
        other_product_id = make_workspace_product(cur, workspace, name="Still Water")
        cur.execute(
            "insert into product_alias (tenant_id,workspace_product_id,alias_text) "
            "values (%s,%s,'water case')",
            (workspace.tenant_id, product_id),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "insert into product_alias (tenant_id,workspace_product_id,alias_text) "
                "values (%s,%s,'Water Case')",
                (workspace.tenant_id, other_product_id),
            )
