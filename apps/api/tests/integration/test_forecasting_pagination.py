"""Regression coverage for latest-per-product proposal pagination.

Exercises the real `forecasting_latest_reorder_proposals` RPC through the real service against a
real Postgres, the same way every other integration test in this suite does it — via
`PsycopgSupabaseClient` wrapping a raw connection with `act_as()` setting the real RLS context,
not a real end-to-end HTTP call through PostgREST. This repo's CI "Backend tests" job runs a bare
Postgres service container with no PostgREST/GoTrue layer at all (see .github/workflows/ci.yml's
schema-bootstrap step); a test that calls `authenticated_client()` for a real HTTP round trip
cannot pass there regardless of correctness, which is why no other integration test in this suite
does that.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    delete_tenant_scoped_rows,
    make_workspace,
)
from integration.quotation_helpers import PsycopgSupabaseClient
from procurepilot_api.modules.forecasting import service as forecasting_service_module
from procurepilot_api.modules.forecasting.service import ForecastingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with the forecasting migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


def _service(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> ForecastingService:
    service = ForecastingService()
    monkeypatch.setattr(
        forecasting_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(conn),
    )
    return service


def _insert_large_proposal_history(
    cur: psycopg.Cursor, workspace: Workspace
) -> tuple[str, str]:
    today = date.today()
    target_proposal_id = ""
    target_product_id = ""
    base_time = datetime.now(UTC)

    for index in range(1002):
        canonical_id, product_id, forecast_id, proposal_id = (uuid4() for _ in range(4))
        is_target = index == 0
        name = "Oldest target product" if is_target else f"Recent product {index}"
        created_at = base_time - timedelta(days=2000 if is_target else index)
        cur.execute(
            "insert into canonical_product (id,name,base_unit) values (%s,%s,'each')",
            (canonical_id, name),
        )
        cur.execute(
            """insert into workspace_product
               (id,tenant_id,canonical_product_id,tenant_name)
               values (%s,%s,%s,%s)""",
            (product_id, workspace.tenant_id, canonical_id, name),
        )
        cur.execute(
            """insert into demand_forecast (
                 id,tenant_id,workspace_product_id,source_fingerprint,model_version,
                 horizon_days,source_window_start,source_window_end,observed_history_days,
                 expected_daily_demand,expected_demand,uncertainty_lower,uncertainty_upper,
                 stock_on_hand,suggested_quantity,confidence,state,release_posture,
                 valid_from,valid_until
               ) values (%s,%s,%s,%s,'pagination-test',30,%s,%s,200,
                         1.5,45,40,50,10,35,'high','ready','g3_unmet',
                         now(),now()+interval '30 days')""",
            (
                forecast_id,
                workspace.tenant_id,
                product_id,
                f"pagination-{uuid4()}",
                today - timedelta(days=90),
                today,
            ),
        )
        cur.execute(
            """insert into reorder_proposal
               (id,tenant_id,demand_forecast_id,workspace_product_id,status,created_at)
               values (%s,%s,%s,%s,'open',%s)""",
            (proposal_id, workspace.tenant_id, forecast_id, product_id, created_at),
        )
        if is_target:
            target_proposal_id = str(proposal_id)
            target_product_id = str(product_id)
    return target_proposal_id, target_product_id


def test_list_proposals_keeps_products_older_than_first_thousand_rows(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An old unique product remains reachable after >1001 newer tenant proposals."""
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "ForecastPagination")
        target_proposal_id, target_product_id = _insert_large_proposal_history(cur, workspace)
    conn.commit()

    service = _service(conn, monkeypatch)
    try:
        with conn.cursor() as cur:
            act_as(cur, workspace)

        found: set[str] = set()
        cursor = None
        while True:
            page = service.list_proposals(bearer_token="token", cursor=cursor, limit=100)
            found.update(str(item.id) for item in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert target_proposal_id in found
        assert target_product_id
    finally:
        with conn.cursor() as cur:
            cur.execute("reset role")
            delete_tenant_scoped_rows(cur, workspace.tenant_id)
        conn.commit()
