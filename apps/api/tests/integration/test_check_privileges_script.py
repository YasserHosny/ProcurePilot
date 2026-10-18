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


def test_a_privilege_granted_to_public_is_reported() -> None:
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute("grant select, truncate on push_notification to public")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert "anon holds SELECT on push_notification" in failures
    assert "authenticated holds TRUNCATE on push_notification" in failures


def test_a_privilege_inherited_through_a_role_is_reported() -> None:
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute("create role zz_privilege_check_inherited nologin")
            conn.execute("grant trigger on push_notification to zz_privilege_check_inherited")
            conn.execute("grant zz_privilege_check_inherited to authenticated")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert "authenticated holds TRIGGER on push_notification" in failures


def test_a_table_open_to_clients_through_public_without_forced_rls_is_reported() -> None:
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute("create table public.zz_privilege_check_probe (id int)")
            conn.execute("revoke all on public.zz_privilege_check_probe from anon, authenticated")
            conn.execute("grant select on public.zz_privilege_check_probe to public")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert (
        "zz_privilege_check_probe is accessible to a client role without ENABLE + FORCE "
        "row-level security"
    ) in failures


@pytest.mark.parametrize("privilege", ["UPDATE", "DELETE"])
def test_a_mutable_grant_on_audit_event_is_reported(privilege: str) -> None:
    with connect(TEST_DATABASE_URL) as conn:
        try:
            conn.execute(f"grant {privilege.lower()} on audit_event to authenticated")
            failures, _warnings = run(conn, None)
        finally:
            conn.rollback()
    assert f"authenticated holds {privilege} on audit_event, which is append-only" in failures
