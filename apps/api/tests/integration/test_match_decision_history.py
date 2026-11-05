"""P-154 on real Postgres: the correction chain and who decided, scoped by RLS."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_line,
    make_quotation,
    make_supplier,
)
from integration.test_match_decision_supersession import _decide
from procurepilot_api.config import Settings
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.matching import service as module
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Case:
    conn: psycopg.Connection
    ws: Workspace
    other: Workspace
    line: UUID
    first: UUID
    second: UUID
    service: MatchingService


@pytest.fixture
def case(monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    conn_iter = connection()
    conn = next(conn_iter)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "decision-history")
        other = make_workspace(cur, "decision-history-other")
        old = make_workspace_product(cur, ws, name="Old oil")
        new = make_workspace_product(cur, ws, name="Right oil")
        quote = make_quotation(cur, ws, supplier_id=make_supplier(cur, ws), status="reviewed")
        line = make_line(cur, ws, quote)
        first = _decide(cur, ws, line, old, automatic=True)
        second = _decide(cur, ws, line, new, supersedes=first)
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    service = MatchingService(Settings())
    try:
        yield Case(conn, ws, other, line, first, second, service)
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
        conn_iter.close()


def test_history_returns_the_chain_oldest_first_with_who_decided(case: Case) -> None:
    with case.conn.cursor() as cur:
        act_as(cur, case.ws)
        cur.execute("select email from membership where id=%s", (case.ws.membership_id,))
        email = cur.fetchone()[0]
    result = case.service.decision_history(bearer_token="t", line_id=case.line)
    assert [d.id for d in result.items] == [case.first, case.second]
    assert result.items[0].is_automatic is True
    assert result.items[0].decided_by_email is None
    assert result.items[1].supersedes_decision_id == case.first
    assert result.items[1].decided_by == case.ws.membership_id
    assert result.items[1].decided_by_email == email


def test_another_tenants_line_reads_as_not_found(case: Case) -> None:
    with case.conn.cursor() as cur:
        act_as(cur, case.other)
    with pytest.raises(NotFoundError):
        case.service.decision_history(bearer_token="t", line_id=case.line)
