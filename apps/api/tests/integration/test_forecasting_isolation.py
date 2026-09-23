"""R4.0 demand_forecast and reorder_proposal cross-tenant isolation tests."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    make_workspace,
    make_workspace_product,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a hosted Postgres with migrations applied",
)

R4_TABLES = ("demand_forecast", "reorder_proposal")


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _insert_forecast(
    cur: psycopg.Cursor,
    workspace: Workspace,
    product_id: UUID,
    *,
    label: str,
) -> UUID:
    cur.execute("reset role")
    cur.execute("set local role service_role")
    forecast_id = uuid4()
    today = date.today()
    cur.execute(
        """
        insert into demand_forecast (
          id, tenant_id, workspace_product_id, source_fingerprint, model_version,
          horizon_days, source_window_start, source_window_end, observed_history_days,
          expected_daily_demand, expected_demand, uncertainty_lower, uncertainty_upper,
          stock_on_hand, suggested_quantity, confidence, state, release_posture,
          valid_from, valid_until
        ) values (
          %s, %s, %s, %s, 'forecast-v1', 30, %s, %s, 200,
          1.5, 45.0, 40.0, 50.0, 10.0, 35.0,
          'high', 'ready', 'g3_unmet',
          now(), now() + interval '30 days'
        )
        """,
        (
            forecast_id,
            workspace.tenant_id,
            product_id,
            f"{label}-fp-{uuid4().hex[:8]}",
            today - timedelta(days=90),
            today,
        ),
    )
    return forecast_id


def _insert_proposal(
    cur: psycopg.Cursor,
    workspace: Workspace,
    forecast_id: UUID,
    product_id: UUID,
) -> UUID:
    cur.execute("reset role")
    cur.execute("set local role service_role")
    proposal_id = uuid4()
    cur.execute(
        """
        insert into reorder_proposal
          (id, tenant_id, demand_forecast_id, workspace_product_id, status)
        values (%s, %s, %s, %s, 'open')
        """,
        (proposal_id, workspace.tenant_id, forecast_id, product_id),
    )
    return proposal_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_workspaces(
    tmp_path: object,
) -> tuple[psycopg.Connection, Workspace, UUID, UUID, Workspace, UUID, UUID]:
    """Two isolated tenants each with one forecast + proposal."""
    with psycopg.connect(TEST_DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            ws_a = make_workspace(cur, "IsoForecastA")
            ws_b = make_workspace(cur, "IsoForecastB")

            prod_a = make_workspace_product(cur, ws_a, name="Product A")
            prod_b = make_workspace_product(cur, ws_b, name="Product B")

            fc_a = _insert_forecast(cur, ws_a, prod_a, label="TenantA")
            fc_b = _insert_forecast(cur, ws_b, prod_b, label="TenantB")

            prop_a = _insert_proposal(cur, ws_a, fc_a, prod_a)
            prop_b = _insert_proposal(cur, ws_b, fc_b, prod_b)

            conn.commit()
        yield conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b


# ---------------------------------------------------------------------------
# Cross-tenant demand_forecast isolation
# ---------------------------------------------------------------------------


def test_tenant_a_cannot_see_tenant_b_forecasts(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_a)
        cur.execute(
            "select id from demand_forecast where id = %s", (fc_b,)
        )
        assert cur.fetchone() is None, "Tenant A must not see Tenant B's forecast"


def test_tenant_b_cannot_see_tenant_a_forecasts(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_b)
        cur.execute(
            "select id from demand_forecast where id = %s", (fc_a,)
        )
        assert cur.fetchone() is None, "Tenant B must not see Tenant A's forecast"


def test_tenant_a_list_contains_only_own_forecasts(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_a)
        cur.execute("select id from demand_forecast")
        ids = {row[0] for row in cur.fetchall()}
        assert fc_a in ids
        assert fc_b not in ids


# ---------------------------------------------------------------------------
# Cross-tenant reorder_proposal isolation
# ---------------------------------------------------------------------------


def test_tenant_a_cannot_see_tenant_b_proposals(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_a)
        cur.execute(
            "select id from reorder_proposal where id = %s", (prop_b,)
        )
        assert cur.fetchone() is None, "Tenant A must not see Tenant B's proposal"


def test_tenant_b_cannot_see_tenant_a_proposals(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_b)
        cur.execute(
            "select id from reorder_proposal where id = %s", (prop_a,)
        )
        assert cur.fetchone() is None, "Tenant B must not see Tenant A's proposal"


def test_tenant_a_list_contains_only_own_proposals(two_workspaces: object) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        act_as(cur, ws_a)
        cur.execute("select id from reorder_proposal")
        ids = {row[0] for row in cur.fetchall()}
        assert prop_a in ids
        assert prop_b not in ids


# ---------------------------------------------------------------------------
# Release posture immutability
# ---------------------------------------------------------------------------


def test_demand_forecast_release_posture_is_always_g3_unmet(
    two_workspaces: object,
) -> None:
    conn, ws_a, fc_a, prop_a, ws_b, fc_b, prop_b = two_workspaces
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role service_role")
        cur.execute("select release_posture from demand_forecast")
        postures = {row[0] for row in cur.fetchall()}
        assert postures == {"g3_unmet"}, (
            f"All forecasts must carry g3_unmet posture; found: {postures}"
        )
