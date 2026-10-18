"""``pnpm db:check-privileges`` must pass on a database built from the migrations, and fail when a
client role is given a right the migrations never grant."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

import pytest

from procurepilot_api.db import connect

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

_SCRIPT = Path(__file__).parents[2] / "scripts" / "check_privileges.py"
run = runpy.run_path(_SCRIPT)["run"]


def test_migrated_database_passes_every_check() -> None:
    with connect(TEST_DATABASE_URL) as conn:
        failures, _warnings = run(conn, None)
    assert failures == []


def test_an_ungranted_client_privilege_is_reported() -> None:
    """The grant is made inside a transaction that is rolled back, so nothing persists."""
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute("grant truncate, update on push_notification to authenticated")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert "authenticated holds TRUNCATE on push_notification" in failures


def test_a_table_without_forced_rls_open_to_clients_is_reported() -> None:
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute("create table public.zz_privilege_check_probe (id int)")
            conn.execute("grant select on public.zz_privilege_check_probe to authenticated")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert (
        "zz_privilege_check_probe is accessible to a client role without ENABLE + FORCE "
        "row-level security"
    ) in failures
