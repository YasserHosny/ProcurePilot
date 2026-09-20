"""Database-backed R3.4 tenant isolation coverage.

This deliberately runs as the real ``authenticated`` role. Mocked services cannot prove that
the partner-era refresh state is protected by PostgreSQL RLS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import make_supplier
from integration.smart_compare_helpers import cleanup_workspace

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres database with R3.4 migrations",
)


def test_refresh_schedule_is_isolated_between_tenants() -> None:
    assert TEST_DATABASE_URL
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            tenant_a = make_workspace(cur, "r34-isolation-alpha")
            tenant_b = make_workspace(cur, "r34-isolation-beta")
            supplier_a = make_supplier(cur, tenant_a, "Alpha Supplier")
            product_a = make_workspace_product(cur, tenant_a, name="Alpha Product")
            schedule_id = uuid4()

            act_as(cur, tenant_a)
            cur.execute(
                """
                insert into offer_refresh_schedule
                  (id, tenant_id, workspace_product_id, supplier_id, next_refresh_at,
                   last_observed_at)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    schedule_id,
                    tenant_a.tenant_id,
                    product_a,
                    supplier_a,
                    datetime.now(UTC) + timedelta(days=14),
                    datetime.now(UTC),
                ),
            )
            conn.commit()

            act_as(cur, tenant_b)
            cur.execute(
                "select id from offer_refresh_schedule where id = %s",
                (schedule_id,),
            )
            assert cur.fetchone() is None

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    """
                    insert into offer_refresh_schedule
                      (tenant_id, workspace_product_id, supplier_id, next_refresh_at)
                    values (%s, %s, %s, now())
                    """,
                    (tenant_a.tenant_id, product_a, supplier_a),
                )

            conn.rollback()
            cur.execute("set local role service_role")
            cur.execute(
                "select id, tenant_id from offer_refresh_schedule where id = %s",
                (schedule_id,),
            )
            assert cur.fetchone() == (schedule_id, tenant_a.tenant_id)

    cleanup_workspace(tenant_a)
    cleanup_workspace(tenant_b)
