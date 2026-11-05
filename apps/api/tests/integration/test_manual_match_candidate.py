"""P-151 A2 on real Postgres: a manual candidate is recorded under RLS and can be decided."""

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
from integration.test_landed_cost_workflow import _member
from procurepilot_api.config import Settings
from procurepilot_api.errors import ConflictError, NotFoundError
from procurepilot_api.modules.matching import resolution_service as module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Case:
    conn: psycopg.Connection
    ws: Workspace
    other: Workspace
    line: UUID
    product: UUID
    archived: UUID
    foreign_product: UUID
    service: MatchResolutionService

    def add(self, product: UUID):  # noqa: ANN201
        return self.service.add_manual_candidate(
            bearer_token="test", member=_member(self.ws), line_id=self.line, product_id=product
        )


@pytest.fixture
def case(monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    conn_iter = connection()
    conn = next(conn_iter)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "manual-cand")
        other = make_workspace(cur, "manual-cand-other")
        product = make_workspace_product(cur, ws, name="Sunflower oil")
        archived = make_workspace_product(cur, ws, name="Retired oil")
        cur.execute("update workspace_product set status='archived' where id=%s", (archived,))
        foreign = make_workspace_product(cur, other, name="Other tenant oil")
        quote = make_quotation(cur, ws, supplier_id=make_supplier(cur, ws), status="reviewed")
        line = make_line(cur, ws, quote)
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    with conn.cursor() as cur:
        act_as(cur, ws)
    service = MatchResolutionService(Settings())
    try:
        yield Case(conn, ws, other, line, product, archived, foreign, service)
    finally:
        with conn.cursor() as cur:
            reset_role(cur)
        conn_iter.close()


def test_records_once_and_replays_the_same_candidate(case: Case) -> None:
    first = case.add(case.product)
    again = case.add(case.product)
    assert again.id == first.id
    assert first.reasons.manual is True
    assert first.scoring_version == "manual-v1"
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from match_candidate where quotation_line_id=%s", (case.line,))
        assert cur.fetchone()[0] == 1


def test_another_tenants_product_reads_as_not_found(case: Case) -> None:
    with pytest.raises(NotFoundError):
        case.add(case.foreign_product)


def test_an_archived_product_is_refused(case: Case) -> None:
    with pytest.raises(ConflictError):
        case.add(case.archived)
