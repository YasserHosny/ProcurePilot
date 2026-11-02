"""Reading an already-prepared quotation's matches is a constant number of queries (PPS-133).

Each PostgREST call is a network round trip; on hosted the matches read was 5–6 s for four lines
because it re-ran preparation and read candidates, products, decisions, tasks and landed costs
line by line.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
    psycopg,
)
from integration.quotation_helpers import (
    PsycopgRpcQuery,
    PsycopgSupabaseClient,
    PsycopgTableQuery,
    ensure_quotation_reference_data,
    make_document,
    make_quotation,
    make_supplier,
)
from integration.test_quotation_audit import _member, _PsycopgAuditWriter
from procurepilot_api.modules.landed_cost import service as landed_cost_module
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")

# One read each: quotation, lines, line fields, decisions, tasks, candidates, products,
# canonical products, landed costs, supplier, document, reviewer.
MAX_PREPARED_ROUND_TRIPS = 12

ALIASED_LINES = ("Tomatoes case 10 kg", "Onions sack 5 kg", "Olive oil tin 4 l")
REVIEW_LINE = "Acme Oragnic Tomato Passatta"


@pytest.fixture
def scenario(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    with contextmanager(connection)() as conn:
        with conn.cursor() as cur:
            ensure_quotation_reference_data(cur)
            workspace = make_workspace(cur, "matches-round-trips")
            supplier_id = make_supplier(cur, workspace, name="Round Trip Supplier")
            quotation_id = make_quotation(
                cur,
                workspace,
                document_id=make_document(cur, workspace, filename="round-trips.pdf"),
                supplier_id=supplier_id,
                status="reviewed",
                arithmetic_status="reconciled",
            )
            for name in ALIASED_LINES:
                product_id = make_workspace_product(cur, workspace, name=name)
                act_as(cur, workspace)
                cur.execute(
                    "insert into product_alias "
                    "(tenant_id,workspace_product_id,alias_text,created_by) values (%s,%s,%s,%s)",
                    (workspace.tenant_id, product_id, name, workspace.membership_id),
                )
            make_workspace_product(cur, workspace, name="Acme Organic Tomato Passata")
            make_workspace_product(cur, workspace, name="Acme Tomato Puree")
            for number, text in enumerate((*ALIASED_LINES, REVIEW_LINE), start=1):
                _make_line(cur, workspace, quotation_id, number, text)
            cur.execute(
                "update quotation set reviewed_by = %s, reviewed_at = now() where id = %s",
                (workspace.membership_id, quotation_id),
            )

        client = PsycopgSupabaseClient(conn)
        writer = _PsycopgAuditWriter(conn)
        for module in (matching_module, landed_cost_module):
            monkeypatch.setattr(module, "authenticated_client", lambda *_args: client)
        monkeypatch.setattr(matching_module, "get_audit_writer", lambda: writer)
        monkeypatch.setattr(
            matching_module.MatchingService,
            "_service_role_client",
            lambda _self: PsycopgSupabaseClient(conn, service_role=True),
        )
        rfq_reads: list[UUID] = []

        def rfq_lines_for_quotation(_settings: object, _member: object, quote_id: UUID) -> None:
            rfq_reads.append(quote_id)

        monkeypatch.setattr(matching_module, "rfq_lines_for_quotation", rfq_lines_for_quotation)
        monkeypatch.setattr(matching_module, "enqueue_guardrail_evaluation", lambda *_a, **_k: None)

        round_trips: Counter[str] = Counter()
        table_execute = PsycopgTableQuery.execute
        rpc_execute = PsycopgRpcQuery.execute

        def counted_table_execute(query: PsycopgTableQuery) -> object:
            round_trips[f"{query._operation} {query._table}"] += 1
            return table_execute(query)

        def counted_rpc_execute(query: PsycopgRpcQuery) -> object:
            round_trips[f"rpc {query._function}"] += 1
            return rpc_execute(query)

        monkeypatch.setattr(PsycopgTableQuery, "execute", counted_table_execute)
        monkeypatch.setattr(PsycopgRpcQuery, "execute", counted_rpc_execute)
        yield SimpleNamespace(
            conn=conn,
            workspace=workspace,
            quotation_id=quotation_id,
            round_trips=round_trips,
            rfq_reads=rfq_reads,
        )


def _make_line(
    cur: psycopg.Cursor, workspace: object, quotation_id: UUID, number: int, text: str
) -> UUID:
    line_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        "insert into quotation_line "
        "(id,tenant_id,quotation_id,line_number,original_text,quantity,pack_count,unit_size,"
        "pack_unit,unit_price_amount,unit_price_currency) "
        "values (%s,%s,%s,%s,%s,2,1,10,'kilogram',12,'GBP')",
        (line_id, workspace.tenant_id, quotation_id, number, text),
    )
    return line_id


def test_prepared_quotation_matches_read_is_constant_round_trips(
    scenario: SimpleNamespace,
) -> None:
    service = MatchingService()
    member = _member(scenario.workspace)
    with scenario.conn.cursor() as cur:
        act_as(cur, scenario.workspace)
    prepared = service.quotation_matches(
        bearer_token="caller-token", member=member, quotation_id=scenario.quotation_id
    )
    states = {state.line.line_number: state for state in prepared.lines}
    assert [states[number].decision is not None for number in (1, 2, 3, 4)] == [
        True,
        True,
        True,
        False,
    ]
    assert all(states[number].landed_cost is not None for number in (1, 2, 3))
    assert states[4].task is not None and states[4].task.status == "open"
    assert states[4].candidates

    scenario.round_trips.clear()
    scenario.rfq_reads.clear()
    again = service.quotation_matches(
        bearer_token="caller-token", member=member, quotation_id=scenario.quotation_id
    )

    assert again == prepared
    total = sum(scenario.round_trips.values())
    assert total <= MAX_PREPARED_ROUND_TRIPS, dict(scenario.round_trips)
    # Nothing to prepare: no RFQ read (a new Postgres connection) and no writes.
    assert scenario.rfq_reads == []
    assert not [key for key in scenario.round_trips if not key.startswith("select ")]
