from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import Mock
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

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
from integration.test_match_alias_learning import _candidate, _open_task
from integration.test_match_decision_supersession import _decide
from integration.test_rfq_aware_matching import make_rfq, reply, settings, wire
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.modules.matching import resolution_service as resolution_module
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.router import router
from procurepilot_api.modules.matching.schemas import MatchCorrectionRequest, MatchResolutionRequest
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@dataclass
class Case:
    conn: psycopg.Connection
    ws: Workspace
    product: UUID
    other_product: UUID
    teacher: UUID
    candidate: UUID
    service: MatchResolutionService
    client: PsycopgSupabaseClient
    enqueued: list[UUID]

    def open_line(
        self, text: str = "دقيق", *, product: UUID | None = None, quote: UUID | None = None
    ) -> tuple[UUID, UUID]:
        with self.conn.cursor() as cur:
            act_as(cur, self.ws)
            quote = quote or make_quotation(
                cur, self.ws, supplier_id=make_supplier(cur, self.ws), status="reviewed"
            )
            line = make_line(cur, self.ws, quote)
            cur.execute("update quotation_line set original_text=%s where id=%s", (text, line))
            candidate = _candidate(cur, self.ws, line, product or self.product)
            _open_task(cur, self.ws, line)
        return line, candidate

    def resolve(self, **kwargs: object) -> object:
        return self.service.resolve(
            bearer_token="test",
            member=_member(self.ws),
            line_id=self.teacher,
            payload=MatchResolutionRequest(
                outcome="same_product", selected_match_candidate_id=self.candidate
            ),
            **kwargs,
        )

    def heads(self, line: UUID) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute("select id from current_match_decision where quotation_line_id=%s", (line,))
            return cur.fetchall()


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


@pytest.fixture
def case(conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch) -> Case:
    enqueued = wire(monkeypatch, conn)
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(resolution_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(resolution_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))
    monkeypatch.setattr(
        resolution_module,
        "enqueue_guardrail_evaluation",
        lambda *_, **kw: enqueued.append(kw["quotation_id"]),
    )

    @contextmanager
    def scoped(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(resolution_module, "_authenticated_db", scoped)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "alias-sweep")
        product = make_workspace_product(cur, ws, name="دقيق")
        other = make_workspace_product(cur, ws, name="Other product")
    result = Case(
        conn,
        ws,
        product,
        other,
        uuid4(),
        uuid4(),
        MatchResolutionService(settings()),
        client,
        enqueued,
    )
    result.teacher, result.candidate = result.open_line()
    return result


@pytest.mark.parametrize("text", ("دقيق", " \u00a0ﺩﻗﻴﻖ\t "))
@pytest.mark.parametrize("reuse_candidate", (True, False))
def test_resolution_sweeps_other_supplier_with_cost_audit_and_response(
    case: Case, text: str, reuse_candidate: bool
) -> None:
    line, candidate = case.open_line(
        text, product=case.product if reuse_candidate else case.other_product
    )
    with case.conn.cursor() as cur:
        cur.execute(
            "update match_task set status='in_progress' where quotation_line_id=%s", (line,)
        )
        cur.execute("select quotation_id from quotation_line where id=%s", (line,))
        quote = cur.fetchone()[0]
        # Another affected line in this quote must not enqueue the quotation twice.
        second = uuid4()
        cur.execute(
            "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text,"
            "quantity,unit_price_amount,unit_price_currency) values (%s,%s,%s,2,'دقيق',2,12,'GBP')",
            (second, case.ws.tenant_id, quote),
        )
        _open_task(cur, case.ws, second)
    key = uuid4()
    result = case.resolve(idempotency_key=key)
    assert set(result.lines_matched_by_same_wording) == {line, second}
    with case.conn.cursor() as cur:
        cur.execute(
            "select id,is_automatic,decided_by,alias_id,learned_from_decision_id,"
            "selected_match_candidate_id,outcome from current_match_decision "
            "where quotation_line_id=%s",
            (line,),
        )
        row = cur.fetchone()
        assert row[1:5] == (True, None, result.alias_id, result.id)
        assert row[6] == "same_product"
        cur.execute("select count(*) from match_candidate where quotation_line_id=%s", (line,))
        assert cur.fetchone()[0] == (1 if reuse_candidate else 2)
        if reuse_candidate:
            assert row[5] == candidate
        else:
            cur.execute(
                "select rank,reasons,scoring_version from match_candidate where id=%s", (row[5],)
            )
            rank, reasons, version = cur.fetchone()
            assert rank == 2
            assert reasons["alias_hit"] is True
            assert reasons["measured"] == {}
            assert version == matching_module.SCORING_VERSION
        cur.execute("select status,resolved_at from match_task where quotation_line_id=%s", (line,))
        status, resolved_at = cur.fetchone()
        assert status == "resolved" and resolved_at is not None
        cur.execute("select match_decision_id from landed_cost where quotation_line_id=%s", (line,))
        assert cur.fetchone()[0] == row[0]
        cur.execute(
            "select target from audit_event where action='matching.alias_sweep_matched' "
            "and target->>'quotation_line_id'=%s",
            (str(line),),
        )
        assert cur.fetchone()[0] == {
            "alias_id": str(result.alias_id),
            "learned_from_decision_id": str(result.id),
            "decision_id": str(row[0]),
            "quotation_line_id": str(line),
        }
    assert case.enqueued.count(quote) == 1
    assert case.resolve(idempotency_key=key).model_dump() == result.model_dump()
    assert case.enqueued.count(quote) == 1


def test_resembling_decided_and_other_tenant_lines_stay_untouched(case: Case) -> None:
    near, _ = case.open_line("دقيق فاخر")
    decided, _ = case.open_line()
    with case.conn.cursor() as cur:
        head = _decide(cur, case.ws, decided, case.other_product)
        other_ws = make_workspace(cur, "sweep-other")
        quote = make_quotation(
            cur, other_ws, supplier_id=make_supplier(cur, other_ws), status="reviewed"
        )
        other_line = make_line(cur, other_ws, quote)
        cur.execute("update quotation_line set original_text='دقيق' where id=%s", (other_line,))
        _open_task(cur, other_ws, other_line)
        act_as(cur, case.ws)
    result = case.resolve()
    assert result.lines_matched_by_same_wording == []
    assert case.heads(near) == []
    assert case.heads(decided) == [(head,)]
    with case.conn.cursor() as cur:
        act_as(cur, other_ws)
        assert case.heads(other_line) == []
        cur.execute("select status from match_task where quotation_line_id=%s", (other_line,))
        assert cur.fetchone()[0] == "open"


def test_sweep_cap(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [case.open_line()[0] for _ in range(4)]
    monkeypatch.setattr(matching_module, "ALIAS_SWEEP_LIMIT", 2, raising=False)
    with case.conn.cursor() as cur:
        for i, line in enumerate(lines):
            cur.execute(
                "update match_task set created_at=now() + %s * interval '1 second' "
                "where quotation_line_id=%s",
                (i, line),
            )
    result = case.resolve()
    assert set(result.lines_matched_by_same_wording) == set(lines[-2:])
    assert len(result.lines_matched_by_same_wording) == 2
    assert sum(bool(case.heads(line)) for line in lines) == 2


def test_rfq_automatic_decision_does_not_sweep(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    sweep = Mock(side_effect=AssertionError("Automatic matches must not sweep"))
    monkeypatch.setattr(MatchingService, "sweep_open_lines_for_alias", sweep, raising=False)
    with case.conn.cursor() as cur:
        rfq = make_rfq(cur, case.ws, [case.product])
        quote = reply(cur, case.ws, rfq, ("دقيق",))
    result = MatchingService(settings()).quotation_matches(
        bearer_token="test", member=_member(case.ws), quotation_id=quote
    )
    assert result.lines[0].decision.is_automatic
    assert case.heads(case.teacher) == []
    sweep.assert_not_called()
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from product_alias")
        assert cur.fetchone()[0] == 0


def test_correcting_teacher_lists_swept_lines_and_correction_teaches(case: Case) -> None:
    swept, _ = case.open_line()
    teacher = case.resolve()
    later, _ = case.open_line()
    key = uuid4()
    response = case.service.correct(
        bearer_token="test",
        member=_member(case.ws),
        line_id=case.teacher,
        payload=MatchCorrectionRequest(
            expected_current_decision_id=teacher.id,
            outcome="same_product",
            selected_match_candidate_id=case.candidate,
        ),
        idempotency_key=key,
    )
    assert response.lines_matched_through_old_wording == [swept]
    assert response.lines_matched_by_same_wording == [later]
    with case.conn.cursor() as cur:
        cur.execute(
            "select learned_from_decision_id from current_match_decision "
            "where quotation_line_id=%s",
            (later,),
        )
        assert cur.fetchone()[0] == response.decision.id


def test_bulk_sweeps_once_per_alias_after_all_human_confirmations(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    second, _ = case.open_line()
    swept, _ = case.open_line(product=case.other_product)
    monkeypatch.setattr(resolution_module, "EXACT_CONFIRM_WORKERS", 1)
    original = MatchingService.sweep_open_lines_for_alias
    spy = Mock()

    def counted(self: MatchingService, *args: object, **kw: object) -> list[UUID]:
        spy(*args, **kw)
        return original(self, *args, **kw)

    monkeypatch.setattr(MatchingService, "sweep_open_lines_for_alias", counted)
    key = uuid4()
    result = case.service.confirm_exact_matches(
        bearer_token="test", member=_member(case.ws), idempotency_key=key
    )
    assert (result.confirmed, result.skipped) == (2, 0)
    assert result.lines_matched_by_same_wording == [swept]
    spy.assert_called_once()
    with case.conn.cursor() as cur:
        cur.execute(
            "select is_automatic from current_match_decision where quotation_line_id=%s", (second,)
        )
        assert cur.fetchone()[0] is False
    later, _ = case.open_line(product=case.other_product)
    replay = case.service.confirm_exact_matches(
        bearer_token="test", member=_member(case.ws), idempotency_key=key
    )
    assert replay == result
    assert case.heads(later) == []
    spy.assert_called_once()


def test_sweep_failure_is_logged_without_failing_resolution(
    case: Case, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    line, _ = case.open_line()
    monkeypatch.setattr(
        MatchingService,
        "sweep_open_lines_for_alias",
        Mock(side_effect=RuntimeError("sweep unavailable")),
        raising=False,
    )
    result = case.resolve()
    assert case.heads(case.teacher) == [(result.id,)]
    assert case.heads(line) == []
    assert result.lines_matched_by_same_wording == []
    assert any(r.exc_info and "sweep unavailable" in str(r.exc_info[1]) for r in caplog.records)


def test_concurrent_root_is_skipped_without_a_sweep_audit(
    case: Case, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    line, _ = case.open_line()
    table = case.client.table

    def race_table(name: str) -> object:
        query = table(name)
        if name == "match_decision":
            insert = query.insert

            def race(payload: dict[str, object]) -> object:
                if payload["quotation_line_id"] == str(line):
                    with case.conn.cursor() as cur:
                        _decide(cur, case.ws, line, case.other_product)
                    query.execute = Mock(
                        side_effect=APIError(
                            {"code": "23505", "message": "one root", "details": "", "hint": ""}
                        )
                    )
                    return query
                return insert(payload)

            query.insert = race
        return query

    monkeypatch.setattr(case.client, "table", race_table)
    result = case.resolve()
    assert result.lines_matched_by_same_wording == []
    assert case.heads(line)
    assert not caplog.records
    with case.conn.cursor() as cur:
        cur.execute("select count(*) from audit_event where action='matching.alias_sweep_matched'")
        assert cur.fetchone()[0] == 0


def test_resolve_http_response_exposes_swept_ids(case: Case) -> None:
    line, _ = case.open_line()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _member(case.ws)
    app.dependency_overrides[bearer_token] = lambda: "test"
    app.dependency_overrides[resolution_module.get_match_resolution_service] = lambda: case.service
    with TestClient(app) as http:
        response = http.post(
            f"/api/v1/quotation-lines/{case.teacher}/match",
            json={
                "outcome": "same_product",
                "selected_match_candidate_id": str(case.candidate),
            },
        )
    assert response.status_code == 200
    assert response.json()["lines_matched_by_same_wording"] == [str(line)]


def test_normalisation_collapses_internal_spaces_and_folds_case_and_unicode(case: Case) -> None:
    with case.conn.cursor() as cur:
        cur.execute(
            "update quotation_line set original_text='Flour Premium' where id=%s", (case.teacher,)
        )
    line, _ = case.open_line("  ＦＬＯＵＲ\t  premium ")
    near, _ = case.open_line("flour premium grade")
    result = case.resolve()
    assert result.lines_matched_by_same_wording == [line]
    assert case.heads(near) == []


def test_correction_learns_a_fresh_alias_and_replays_sweep_response(case: Case) -> None:
    with case.conn.cursor() as cur:
        old = _decide(cur, case.ws, case.teacher, case.other_product, automatic=True)
    line, _ = case.open_line()
    payload = MatchCorrectionRequest(
        expected_current_decision_id=old,
        outcome="same_product",
        selected_match_candidate_id=case.candidate,
    )
    key = uuid4()
    result = case.service.correct(
        bearer_token="test",
        member=_member(case.ws),
        line_id=case.teacher,
        payload=payload,
        idempotency_key=key,
    )
    assert result.decision.alias_id is not None
    assert result.lines_matched_by_same_wording == [line]
    assert result.lines_matched_through_old_wording == []
    later, _ = case.open_line()
    replay = case.service.correct(
        bearer_token="test",
        member=_member(case.ws),
        line_id=case.teacher,
        payload=payload,
        idempotency_key=key,
    )
    assert replay == result
    assert case.heads(later) == []


def test_reused_alias_in_single_resolution_also_sweeps(case: Case) -> None:
    first = case.resolve()
    case.teacher, case.candidate = case.open_line()
    line, _ = case.open_line()
    second = case.resolve()
    assert second.alias_id == first.alias_id
    assert second.lines_matched_by_same_wording == [line]
    with case.conn.cursor() as cur:
        cur.execute(
            "select learned_from_decision_id from current_match_decision "
            "where quotation_line_id=%s",
            (line,),
        )
        assert cur.fetchone()[0] == second.id


def test_bulk_sweep_guardrail_failure_is_logged_without_failing_confirmation(
    case: Case, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    line, _ = case.open_line(product=case.other_product)
    with case.conn.cursor() as cur:
        cur.execute("select quotation_id from quotation_line where id=%s", (line,))
        swept_quote = cur.fetchone()[0]

    def enqueue(*_: object, **kwargs: object) -> None:
        if kwargs["quotation_id"] == swept_quote:
            raise RuntimeError("sweep guardrail unavailable")

    monkeypatch.setattr(resolution_module, "enqueue_guardrail_evaluation", enqueue)
    monkeypatch.setattr(resolution_module, "EXACT_CONFIRM_WORKERS", 1)
    result = case.service.confirm_exact_matches(bearer_token="test", member=_member(case.ws))
    assert result.confirmed == 1
    assert result.lines_matched_by_same_wording == [line]
    assert any(
        r.exc_info and "sweep guardrail unavailable" in str(r.exc_info[1]) for r in caplog.records
    )
