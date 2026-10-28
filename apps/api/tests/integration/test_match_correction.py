from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_line,
    make_quotation,
    make_supplier,
)
from integration.test_landed_cost_workflow import _member, _PsycopgAuditWriter
from integration.test_match_decision_supersession import _decide
from procurepilot_api.config import Settings
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.matching import resolution_service as module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.router import router
from procurepilot_api.modules.matching.schemas import (
    MatchCorrectionRequest,
    MatchCorrectionResponse,
)

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Case:
    conn: psycopg.Connection
    ws: Workspace
    line: UUID
    old_product: UUID
    new_product: UUID
    head: UUID
    candidate: UUID
    service: MatchResolutionService
    enqueued: list[UUID]

    def correct(self, *, key: UUID | None = None, **changes: object) -> MatchCorrectionResponse:
        body = {
            "expected_current_decision_id": self.head,
            "outcome": "same_product",
            "selected_match_candidate_id": self.candidate,
            **changes,
        }
        return self.service.correct(
            bearer_token="test",
            member=_member(self.ws),
            line_id=self.line,
            payload=MatchCorrectionRequest.model_validate(body),
            idempotency_key=key or uuid4(),
        )


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


@pytest.fixture
def case(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "match-correction")
        old = make_workspace_product(cur, ws, name="Old oil")
        new = make_workspace_product(cur, ws, name="Correct rice")
        quote = make_quotation(cur, ws, supplier_id=make_supplier(cur, ws), status="reviewed")
        line = make_line(cur, ws, quote)
        head = _decide(cur, ws, line, old, automatic=True)
        candidate = uuid4()
        cur.execute(
            "insert into match_candidate (id,tenant_id,quotation_line_id,"
            "candidate_workspace_product_id,confidence,reasons,rank,scoring_version,"
            "embedding_model) "
            "values (%s,%s,%s,%s,0.9,%s,2,'matching-score-v2','stub-hash-v1')",
            (
                candidate,
                ws.tenant_id,
                line,
                new,
                psycopg.types.json.Jsonb(
                    {"alias_hit": False, "gtin_match": False, "supplier_code_match": False}
                ),
            ),
        )
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))

    @contextmanager
    def scoped(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(module, "_authenticated_db", scoped, raising=False)
    enqueued: list[UUID] = []
    monkeypatch.setattr(
        module,
        "enqueue_guardrail_evaluation",
        lambda *_, **kw: enqueued.append(kw["quotation_id"]),
    )
    service = MatchResolutionService(Settings())
    service._landed_cost.compute_for_line_with_client(
        client=client, member=_member(ws), line_id=line
    )
    yield Case(conn, ws, line, old, new, head, candidate, service, enqueued)


def test_correction_appends_human_head_cost_audit_and_replays_exact_response(case: Case) -> None:
    key = uuid4()
    result = case.correct(key=key)
    assert result.superseded_decision_id == case.head
    assert result.decision.supersedes_decision_id == case.head
    assert result.decision.is_automatic is False
    assert result.decision.decided_by == case.ws.membership_id
    assert result.decision.matched_product.id == case.new_product
    assert result.lines_matched_through_old_wording == []
    assert case.correct(key=key).model_dump() == result.model_dump()
    with case.conn.cursor() as cur:
        cur.execute(
            "select id from current_match_decision where quotation_line_id=%s", (case.line,)
        )
        assert cur.fetchone()[0] == result.decision.id
        cur.execute("select count(*) from match_decision where quotation_line_id=%s", (case.line,))
        assert cur.fetchone()[0] == 2
        cur.execute(
            "select match_decision_id from landed_cost where quotation_line_id=%s", (case.line,)
        )
        assert {r[0] for r in cur.fetchall()} == {case.head, result.decision.id}
        cur.execute("select target from audit_event where action='matching.decision_corrected'")
        target = cur.fetchone()[0]
        assert target["superseded_decision_id"] == str(case.head)
        assert target["decision_id"] == str(result.decision.id)
        assert target["from_product_id"] == str(case.old_product)
        assert target["to_product_id"] == str(case.new_product)
    assert len(case.enqueued) == 1


def assert_conflict(case: Case, reason: str, **changes: object) -> None:
    from procurepilot_api.errors import ConflictError

    with pytest.raises(ConflictError) as exc:
        case.correct(**changes)
    assert exc.value.status_code == 409
    assert exc.value.details["reason"] == reason


def test_stale_head_and_reused_key(case: Case) -> None:
    key = uuid4()
    case.correct(key=key)
    assert_conflict(case, "decision_changed")
    assert_conflict(case, "idempotency_key_reused", key=key, learn_alias=False)


@pytest.mark.parametrize("status", ("draft", "submitted", "approved", "ordered"))
def test_live_request_locks_the_match_until_withdrawn(case: Case, status: str) -> None:
    request = uuid4()
    with case.conn.cursor() as cur:
        branch = uuid4()
        cur.execute(
            "insert into branch (id,tenant_id,name) values (%s,%s,'Main')",
            (branch, case.ws.tenant_id),
        )
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status) values (%s,%s,%s,%s,current_date+7,%s)",
            (request, case.ws.tenant_id, branch, case.ws.membership_id, status),
        )
        cur.execute(
            "insert into purchase_request_line (tenant_id,purchase_request_id,"
            "workspace_product_id,quantity,estimated_unit_price_source_landed_cost_id) "
            "select %s,%s,%s,2,id from landed_cost where match_decision_id=%s",
            (case.ws.tenant_id, request, case.old_product, case.head),
        )
    from procurepilot_api.errors import ConflictError

    with pytest.raises(ConflictError) as exc:
        case.correct()
    assert exc.value.details == {
        "reason": "line_on_purchase_request",
        "purchase_request_id": str(request),
    }
    with case.conn.cursor() as cur:
        cur.execute("update purchase_request set status='withdrawn' where id=%s", (request,))
    assert case.correct().decision.supersedes_decision_id == case.head


def test_live_request_lock_holds_for_a_buyer_who_cannot_see_that_request(case: Case) -> None:
    """A buyer assigned to branch A cannot read branch B's requests (purchase_request RLS), but a
    branch-B request priced from this match still locks it: the check must not depend on what the
    caller can see."""
    from integration.test_purchase_requests import _assign_branch, _make_member
    from procurepilot_api.errors import ConflictError

    request = uuid4()
    with case.conn.cursor() as cur:
        cur.execute("reset role")
        branch_a, branch_b = uuid4(), uuid4()
        for branch, name in ((branch_a, "Branch A"), (branch_b, "Branch B")):
            cur.execute(
                "insert into branch (id,tenant_id,name) values (%s,%s,%s)",
                (branch, case.ws.tenant_id, name),
            )
        buyer = _make_member(cur, case.ws.tenant_id, f"buyer-{uuid4().hex[:8]}", "buyer")
        _assign_branch(cur, case.ws, buyer, branch_a)
        cur.execute(
            "insert into purchase_request (id,tenant_id,branch_id,requested_by_membership_id,"
            "required_by_date,status) values (%s,%s,%s,%s,current_date+7,'submitted')",
            (request, case.ws.tenant_id, branch_b, case.ws.membership_id),
        )
        cur.execute(
            "insert into purchase_request_line (tenant_id,purchase_request_id,"
            "workspace_product_id,quantity,estimated_unit_price_source_landed_cost_id) "
            "select %s,%s,%s,2,id from landed_cost where match_decision_id=%s",
            (case.ws.tenant_id, request, case.old_product, case.head),
        )
        act_as(cur, buyer)
        cur.execute("select count(*) from purchase_request where id=%s", (request,))
        assert cur.fetchone()[0] == 0  # the buyer really cannot see it

    with pytest.raises(ConflictError) as exc:
        case.service.correct(
            bearer_token="test",
            member=_member(buyer),
            line_id=case.line,
            payload=MatchCorrectionRequest.model_validate(
                {
                    "expected_current_decision_id": case.head,
                    "outcome": "same_product",
                    "selected_match_candidate_id": case.candidate,
                }
            ),
            idempotency_key=uuid4(),
        )
    assert exc.value.details["reason"] == "line_on_purchase_request"


def test_alias_conflict_does_not_change_old_alias_and_is_replayed(case: Case) -> None:
    with case.conn.cursor() as cur:
        cur.execute(
            "insert into product_alias (tenant_id,workspace_product_id,alias_text,created_by) "
            "values (%s,%s,'Tomatoes case 10 kg',%s)",
            (case.ws.tenant_id, case.old_product, case.ws.membership_id),
        )
    key = uuid4()
    result = case.correct(key=key)
    assert result.alias_conflict_product_id == case.old_product
    assert result.decision.alias_id is None
    assert case.correct(key=key).model_dump() == result.model_dump()
    with case.conn.cursor() as cur:
        cur.execute("select workspace_product_id from product_alias")
        assert cur.fetchall() == [(case.old_product,)]


def test_opt_out_of_alias_learning(case: Case) -> None:
    assert case.correct(learn_alias=False).decision.alias_id is None
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from product_alias")
        assert cur.fetchone()[0] == 0


def test_no_decision_and_cross_tenant_are_distinct_without_existence_leak(case: Case) -> None:
    from procurepilot_api.errors import ConflictError, NotFoundError

    with case.conn.cursor() as cur:
        quote = make_quotation(cur, case.ws, status="reviewed")
        line = make_line(cur, case.ws, quote)
    payload = MatchCorrectionRequest(
        expected_current_decision_id=case.head,
        outcome="same_product",
        selected_match_candidate_id=case.candidate,
    )
    with pytest.raises(ConflictError) as exc:
        case.service.correct(
            bearer_token="test",
            member=_member(case.ws),
            line_id=line,
            payload=payload,
            idempotency_key=uuid4(),
        )
    assert exc.value.details["reason"] == "no_decision"
    with case.conn.cursor() as cur:
        other = make_workspace(cur, "correction-other")
        act_as(cur, other)
    with pytest.raises(NotFoundError):
        case.service.correct(
            bearer_token="test",
            member=_member(other),
            line_id=case.line,
            payload=payload,
            idempotency_key=uuid4(),
        )


def test_route_requires_idempotency_and_returns_conflict_envelope(case: Case) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _member(case.ws)
    app.dependency_overrides[bearer_token] = lambda: "test"
    app.dependency_overrides[module.get_match_resolution_service] = lambda: case.service
    with TestClient(app) as client:
        path = f"/api/v1/quotation-lines/{case.line}/match/corrections"
        body = {
            "expected_current_decision_id": str(uuid4()),
            "outcome": "same_product",
            "selected_match_candidate_id": str(case.candidate),
        }
        assert client.post(path, json=body).status_code == 422
        response = client.post(path, json=body, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 409
        assert response.json()["details"]["reason"] == "decision_changed"


def test_new_product_correction_uses_catalogue_creation(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.modules.catalogue import service as catalogue_module

    client = PsycopgSupabaseClient(case.conn)
    monkeypatch.setattr(catalogue_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(
        catalogue_module,
        "create_client",
        lambda *_: PsycopgSupabaseClient(case.conn, service_role=True),
    )
    monkeypatch.setattr(
        catalogue_module, "get_audit_writer", lambda: _PsycopgAuditWriter(case.conn)
    )
    monkeypatch.setattr(
        catalogue_module.BillingService, "ensure_can_add_active_product", lambda *_, **__: None
    )
    key = uuid4()
    changes = {
        "outcome": "no_match_new_product",
        "selected_match_candidate_id": None,
        "new_product": {
            "tenant_name": "New flour",
            "base_unit": "kilogram",
            "pack": {"pack_count": 1, "unit_size": "10"},
        },
    }
    result = case.correct(key=key, **changes)
    assert result.decision.outcome == "no_match_new_product"
    assert result.decision.matched_product.tenant_name == "New flour"
    assert result.decision.selected_match_candidate_id is None
    assert result.decision.alias_id is not None
    assert case.correct(key=key, **changes).model_dump() == result.model_dump()


def test_candidate_from_another_line_is_refused(case: Case) -> None:
    with case.conn.cursor() as cur:
        quote = make_quotation(cur, case.ws, status="reviewed")
        other_line = make_line(cur, case.ws, quote)
        _decide(cur, case.ws, other_line, case.new_product)
        cur.execute(
            "select selected_match_candidate_id from current_match_decision "
            "where quotation_line_id=%s",
            (other_line,),
        )
        candidate = cur.fetchone()[0]
    assert_conflict(case, "candidate_not_valid_for_line", selected_match_candidate_id=candidate)


def test_dependent_lines_are_current_only_and_replay_keeps_snapshot(case: Case) -> None:
    with case.conn.cursor() as cur:
        quote2 = make_quotation(cur, case.ws, status="reviewed")
        current_dependent = make_line(cur, case.ws, quote2)
        cur.execute(
            "insert into match_decision (tenant_id,quotation_line_id,matched_workspace_product_id,"
            "outcome,is_automatic,confidence,learned_from_decision_id) "
            "values (%s,%s,%s,'no_match_new_product',true,1,%s)",
            (case.ws.tenant_id, current_dependent, case.old_product, case.head),
        )
    key = uuid4()
    result = case.correct(key=key)
    assert result.lines_matched_through_old_wording == [current_dependent]
    # A second correction and a later dependent-line correction cannot change the first replay.
    next_result = case.correct(expected_current_decision_id=result.decision.id, learn_alias=False)
    assert next_result.decision.supersedes_decision_id == result.decision.id
    assert case.correct(key=key).model_dump() == result.model_dump()


def test_correction_waits_for_database_line_lock(case: Case) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep

    from procurepilot_api import db

    with db.connect(TEST_DATABASE_URL or "") as blocker:
        with blocker.cursor() as cur:
            cur.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"correction-line:{case.ws.tenant_id}:{case.line}",),
            )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(case.correct)
            waiting = False
            try:
                deadline = monotonic() + 5
                with blocker.cursor() as cur:
                    while monotonic() < deadline:
                        cur.execute(
                            "select %s = any(pg_blocking_pids(%s))",
                            (blocker.info.backend_pid, case.conn.info.backend_pid),
                        )
                        if cur.fetchone()[0]:
                            waiting = True
                            break
                        if future.done():
                            break
                        sleep(0.01)
            finally:
                blocker.rollback()
            result = future.result(timeout=5)
    assert waiting, "Correction must acquire the tenant+line database lock before reading the head"
    assert result.decision.supersedes_decision_id == case.head


def test_retry_finishes_costing_after_a_failed_side_effect(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.modules.landed_cost.schemas import LandedCost

    compute = case.service._landed_cost.compute_for_line_with_client
    calls = 0

    def fail_once(**kwargs: object) -> LandedCost:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary costing failure")
        return compute(**kwargs)

    monkeypatch.setattr(case.service._landed_cost, "compute_for_line_with_client", fail_once)
    key = uuid4()
    with pytest.raises(RuntimeError, match="temporary costing failure"):
        case.correct(key=key, learn_alias=False)
    result = case.correct(key=key, learn_alias=False)
    assert result.decision.supersedes_decision_id == case.head
    assert case.correct(key=key, learn_alias=False).model_dump() == result.model_dump()
    assert calls == 2
    assert len(case.enqueued) == 1
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from match_decision where quotation_line_id=%s", (case.line,))
        assert cur.fetchone()[0] == 2


def test_failed_replay_mapping_rolls_back_correction_and_same_key_can_retry(
    case: Case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integration.quotation_helpers import PsycopgTableQuery
    from procurepilot_api.errors import ServiceUnavailableError

    key = uuid4()
    sql_execute = psycopg.Cursor.execute
    rest_execute = PsycopgTableQuery.execute
    failures = 0

    def fail_mapping() -> None:
        nonlocal failures
        with case.conn.cursor() as cur:
            cur.execute(
                "select count(*) from match_decision where quotation_line_id=%s", (case.line,)
            )
            assert cur.fetchone()[0] == 2  # Failure really occurs AFTER the decision insert.
        failures += 1
        raise ServiceUnavailableError(details={"dependency": "database"})

    def sql_fail_once(
        cur: psycopg.Cursor, query: object, params: object = None, **kwargs: object
    ) -> object:
        if (
            isinstance(query, str)
            and "insert into match_resolution_idempotency" in query.lower()
            and failures == 0
        ):
            fail_mapping()
        return sql_execute(cur, query, params, **kwargs)

    def rest_fail_once(query: PsycopgTableQuery) -> object:
        if (
            query._table == "match_resolution_idempotency"
            and query._operation == "insert"
            and failures == 0
        ):
            fail_mapping()
        return rest_execute(query)

    monkeypatch.setattr(psycopg.Cursor, "execute", sql_fail_once)
    monkeypatch.setattr(PsycopgTableQuery, "execute", rest_fail_once)
    with pytest.raises(ServiceUnavailableError):
        case.correct(key=key, learn_alias=False)
    assert failures == 1
    with case.conn.cursor() as cur:
        cur.execute(
            "select id from current_match_decision where quotation_line_id=%s", (case.line,)
        )
        assert cur.fetchone()[0] == case.head
        cur.execute("select count(*) from match_decision where quotation_line_id=%s", (case.line,))
        assert cur.fetchone()[0] == 1
        cur.execute(
            "select count(*) from match_resolution_idempotency where idempotency_key=%s", (key,)
        )
        assert cur.fetchone()[0] == 0
    result = case.correct(key=key, learn_alias=False)
    assert result.superseded_decision_id == case.head
    assert case.correct(key=key, learn_alias=False).model_dump() == result.model_dump()
    assert len(case.enqueued) == 1
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from audit_event where action='matching.decision_corrected'")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "select match_decision_id from landed_cost where quotation_line_id=%s", (case.line,)
        )
        assert {row[0] for row in cur.fetchall()} == {case.head, result.decision.id}
