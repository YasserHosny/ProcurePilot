"""Gate spike T058 (spec 025, research D2 / D8): can an operator's audit event name ANOTHER tenant?

Operator actions on a submission (view, status change, attachment URL) must be audited under the
submission's workspace, which is not the operator's own. `record_audit_event` refuses that for any
caller holding a tenant claim (20261018000004), so the question is whether the audit writer's
server-side form, which has no bearer token and runs over DATABASE_URL, is allowed to.

Reading of the migration: it is. The guard only fires for the `anon` / `authenticated` roles or a
caller with a tenant claim, and the server-side form is neither. These tests pin that down against
a real database:

* RED here means the answer is no. Then add
  `supabase/migrations/20261118000650_record_operator_audit_event.sql`, a SECURITY DEFINER
  `record_operator_audit_event(...)` executable only by operators, and have the operator service
  call it instead (that migration is CONDITIONAL and is not written while these tests are green).
* The negative tests are the guard rails: whatever the answer, a MEMBER session (authenticated,
  with claims) must never be able to write into another workspace's history.

Set TEST_DATABASE_URL to a database with the migrations applied; skipped otherwise.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

from integration.catalogue_helpers import Workspace, act_as, make_workspace
from procurepilot_api.shared.audit import AuditEventCreate, AuditWriter

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


def test_server_side_form_records_an_event_for_a_tenant_other_than_the_operators(
    conn: psycopg.Connection,
) -> None:
    """The positive case the operator audit trail depends on (answers research D2 'Verify')."""
    with conn.cursor() as cur:
        operators_home = make_workspace(cur, "auditop")
        submissions_tenant = make_workspace(cur, "auditsub")
    conn.commit()
    try:
        AuditWriter().record(
            AuditEventCreate(
                tenant_id=submissions_tenant.tenant_id,
                actor_membership_id=operators_home.membership_id,
                actor_email="operator@example.test",
                action="feedback.operator_viewed",
                target={"submission_id": "00000000-0000-0000-0000-000000000001"},
                outcome="success",
            )
        )
        with conn.cursor() as cur:
            cur.execute(
                "select tenant_id, actor_membership_id from audit_event "
                "where action = 'feedback.operator_viewed' and tenant_id = %s",
                (submissions_tenant.tenant_id,),
            )
            rows = cur.fetchall()
        assert rows == [(submissions_tenant.tenant_id, operators_home.membership_id)]
    finally:
        _cleanup(conn, operators_home, submissions_tenant)


def test_aggregate_event_without_a_tenant_is_recorded_with_no_tenant(
    conn: psycopg.Connection,
) -> None:
    """`feedback.operator_listed` carries no tenant (research D8): it must not inherit one.

    The writer sends this form through the anon-key RPC (no bearer token, no tenant), so the test
    does the same at the database: role `anon`, no claims.
    """
    marker = "spike-aggregate-marker"
    with conn.cursor() as cur:
        cur.execute("set local role anon")
        cur.execute(
            "select record_audit_event('feedback.operator_listed', 'success'::audit_outcome, "
            "null, null, 'operator@example.test', %s::jsonb, null)",
            (f'{{"marker": "{marker}", "result_count": 3}}',),
        )
        cur.execute("reset role")
        cur.execute(
            "select tenant_id from audit_event where action = 'feedback.operator_listed' "
            "and target ->> 'marker' = %s",
            (marker,),
        )
        assert cur.fetchall() == [(None,)]


def test_a_member_session_still_cannot_write_into_another_workspaces_history(
    conn: psycopg.Connection,
) -> None:
    """Guard rail: the operator path must not have loosened the member-side refusal."""
    with conn.cursor() as cur:
        mine = make_workspace(cur, "auditmine")
        theirs = make_workspace(cur, "audittheirs")
        act_as(cur, mine)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "select record_audit_event('feedback.operator_viewed', 'success'::audit_outcome, "
                "%s, null, null, null, null)",
                (theirs.tenant_id,),
            )


def _cleanup(conn: psycopg.Connection, *workspaces: Workspace) -> None:
    # audit_event is append-only and may keep a reference to the tenant; best effort is enough,
    # because every assertion above filters by ids that exist only for this run.
    try:
        with conn.cursor() as cur:
            cur.execute("reset role")
            for workspace in workspaces:
                cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
                cur.execute("delete from auth.users where id = %s", (workspace.user_id,))
        conn.commit()
    except psycopg.Error:
        conn.rollback()
