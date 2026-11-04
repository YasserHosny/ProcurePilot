# ruff: noqa: F811  (rfq_workspaces is a fixture imported from test_rfq_isolation)
"""A client session can only move an RFQ draft -> sent, and only edit a draft (PPS-213, P-190).

`rfq_update` matches the RFQ's creator but says nothing about *which status* the creator writes,
so a creator talking to the database directly could re-open a cancelled RFQ or mark one
converted without the API's checks and audit event. The `rfq_guard_client_update` trigger
(20261104000600) allows a client role (`authenticated`, `anon`) exactly what the API does
under it -- edit a draft, send it -- and leaves every other status change to the server-side
functions (`cancel_rfq`, `mark_rfq_converted`) and the ingestion worker (`service_role`).
"""

from __future__ import annotations

import os
from uuid import UUID

import psycopg
import pytest

from integration.test_rfq_isolation import (  # noqa: F401  (rfq_workspaces is a pytest fixture)
    RfqWorkspace,
    _act_as,
    _rfq_status,
    rfq_workspaces,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

Workspaces = tuple[psycopg.Connection, RfqWorkspace, RfqWorkspace]


def _set_status(cur: psycopg.Cursor, rfq_id: UUID, status: str) -> None:
    """Put the RFQ in `status` as the table owner (the guard only restricts client roles)."""
    cur.execute("reset role")
    if status == "cancelled":
        cur.execute(
            "update rfq set status = 'cancelled', cancelled_at = now() where id = %s", (rfq_id,)
        )
    else:
        cur.execute(
            "update rfq set status = %s, cancelled_at = null where id = %s", (status, rfq_id)
        )


STORED_STATUSES = ["sent", "responded", "expired", "converted", "cancelled"]
CHANGES = [
    (stored, target)
    for stored in STORED_STATUSES
    for target in ["draft", "sent", "responded", "converted"]
    if stored != target
]


@pytest.mark.parametrize(("stored", "target"), CHANGES)
def test_a_creator_cannot_move_a_non_draft_rfq_by_writing_to_the_database(
    rfq_workspaces: Workspaces, stored: str, target: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _set_status(cur, alpha.rfq_id, stored)
        _act_as(cur, alpha)
        cur.execute("savepoint before_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("update rfq set status = %s where id = %s", (target, alpha.rfq_id))
        cur.execute("rollback to savepoint before_update")
        assert _rfq_status(cur, alpha.rfq_id) == stored


@pytest.mark.parametrize("stored", STORED_STATUSES)
def test_a_creator_cannot_edit_a_non_draft_rfq_by_writing_to_the_database(
    rfq_workspaces: Workspaces, stored: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _set_status(cur, alpha.rfq_id, stored)
        _act_as(cur, alpha)
        cur.execute("savepoint before_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update rfq set needed_by_date = current_date + 30 where id = %s", (alpha.rfq_id,)
            )
        cur.execute("rollback to savepoint before_update")


@pytest.mark.parametrize("target", ["responded", "expired", "converted", "cancelled"])
def test_a_creator_cannot_skip_the_draft_to_sent_step(
    rfq_workspaces: Workspaces, target: str
) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _set_status(cur, alpha.rfq_id, "draft")
        _act_as(cur, alpha)
        cur.execute("savepoint before_update")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            if target == "cancelled":
                cur.execute(
                    "update rfq set status = 'cancelled', cancelled_at = now() where id = %s",
                    (alpha.rfq_id,),
                )
            else:
                cur.execute("update rfq set status = %s where id = %s", (target, alpha.rfq_id))
        cur.execute("rollback to savepoint before_update")
        assert _rfq_status(cur, alpha.rfq_id) == "draft"


def test_a_creator_can_edit_a_draft_and_send_it(rfq_workspaces: Workspaces) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _set_status(cur, alpha.rfq_id, "draft")
        _act_as(cur, alpha)
        cur.execute(
            "update rfq set needed_by_date = current_date + 30 where id = %s", (alpha.rfq_id,)
        )
        assert cur.rowcount == 1
        cur.execute("update rfq set status = 'sent' where id = %s", (alpha.rfq_id,))
        assert cur.rowcount == 1
        assert _rfq_status(cur, alpha.rfq_id) == "sent"


def test_the_server_side_functions_still_move_the_status(rfq_workspaces: Workspaces) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _act_as(cur, alpha)
        cur.execute("select cancel_rfq(%s)", (alpha.rfq_id,))
        assert cur.fetchone()[0] is True
        assert _rfq_status(cur, alpha.rfq_id) == "cancelled"


def test_the_ingestion_worker_role_can_mark_an_rfq_responded(rfq_workspaces: Workspaces) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        cur.execute("reset role")
        cur.execute("set local role service_role")
        cur.execute(
            "update rfq set status = 'responded' where tenant_id = %s and id = %s "
            "and status = 'sent'",
            (alpha.tenant_id, alpha.rfq_id),
        )
        assert cur.rowcount == 1
        assert _rfq_status(cur, alpha.rfq_id) == "responded"


def test_the_table_owner_is_not_restricted(rfq_workspaces: Workspaces) -> None:
    conn, alpha, _beta = rfq_workspaces
    with conn.cursor() as cur:
        _set_status(cur, alpha.rfq_id, "converted")
        assert _rfq_status(cur, alpha.rfq_id) == "converted"
