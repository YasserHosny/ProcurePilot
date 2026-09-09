from __future__ import annotations

import json
from collections.abc import Iterator

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for matching audit integration tests",
)

MATCHING_AUDIT_ACTIONS = (
    "matching.task_routed",
    "matching.auto_accepted",
    "matching.resolved",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


def _record_matching_event(
    cur: psycopg.Cursor,
    workspace: Workspace,
    *,
    action: str,
    quotation_id: str,
    line_id: str,
) -> None:
    act_as(cur, workspace)
    target = {
        "quotation_id": quotation_id,
        "quotation_line_id": line_id,
        "score": "0.8100",
        "scoring_version": "matching-v1",
    }
    cur.execute(
        "select record_audit_event(%s, 'success', %s, %s, %s, %s::jsonb, null)",
        (
            action,
            workspace.tenant_id,
            workspace.membership_id,
            f"{workspace.label}-{workspace.role}@example.test",
            json.dumps(target),
        ),
    )


def test_matching_actions_are_append_only_and_quotation_searchable(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "matching-audit")
        quotation_id = "11111111-1111-1111-1111-111111111111"
        line_id = "22222222-2222-2222-2222-222222222222"

        for action in MATCHING_AUDIT_ACTIONS:
            _record_matching_event(
                cur,
                workspace,
                action=action,
                quotation_id=quotation_id,
                line_id=line_id,
            )

        act_as(cur, workspace)
        cur.execute(
            "select action, actor_membership_id, target from audit_event "
            "where target->>'quotation_id' = %s order by action",
            (quotation_id,),
        )
        rows = cur.fetchall()

        assert {row[0] for row in rows} == set(MATCHING_AUDIT_ACTIONS)
        assert all(row[1] == workspace.membership_id for row in rows)
        assert all(row[2]["quotation_line_id"] == line_id for row in rows)

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "update audit_event set outcome = 'refused' "
                "where target->>'quotation_id' = %s",
                (quotation_id,),
            )


def test_matching_audit_events_are_invisible_to_another_tenant(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        tenant_a = make_workspace(cur, "matching-audit-a")
        tenant_b = make_workspace(cur, "matching-audit-b")
        quotation_id = "33333333-3333-3333-3333-333333333333"

        _record_matching_event(
            cur,
            tenant_a,
            action="matching.resolved",
            quotation_id=quotation_id,
            line_id="44444444-4444-4444-4444-444444444444",
        )

        act_as(cur, tenant_b)
        cur.execute(
            "select id from audit_event where target->>'quotation_id' = %s",
            (quotation_id,),
        )

        assert cur.fetchall() == []
