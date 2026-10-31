from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import UUID, uuid4

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
from integration.test_landed_cost_workflow import _member, _PsycopgAuditWriter
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.modules.rfq import read_api
from procurepilot_api.modules.rfq.read_api import RfqContext

TEXTS = ("أرز بسمتي", "زيت دوار الشمس", "سكر أبيض", "دقيق")
NAMES = (
    "أرز بسمتي (كيس 10 كجم)",
    "زيت دوار الشمس (تنكة 18 لتر)",
    "سكر أبيض (كيس 10 كجم)",
    "دقيق (كيس 45 كجم)",
)

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    yield from connection()


def wire(monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection) -> list[UUID]:
    from procurepilot_api.modules.landed_cost import service as landed_module

    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(landed_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(
        matching_module, "create_client", lambda *_: PsycopgSupabaseClient(conn, service_role=True)
    )
    monkeypatch.setattr(matching_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(matching_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))

    @contextmanager
    def scoped(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    from procurepilot_api.modules.rfq import service as rfq_service

    monkeypatch.setattr(rfq_service, "_authenticated_db", scoped)
    monkeypatch.setattr(matching_module, "_authenticated_db", scoped)
    enqueued: list[UUID] = []
    monkeypatch.setattr(
        matching_module,
        "enqueue_guardrail_evaluation",
        lambda *_, **kw: enqueued.append(kw["quotation_id"]),
    )
    return enqueued


def settings() -> Settings:
    return Settings(
        matching_embedding_provider_mode="stub",
        matching_embedding_model="stub-hash-v1",
        matching_fuzzy_auto_accept_enabled=False,
    )


def reply(
    cur: psycopg.Cursor, ws: Workspace, rfq_id: UUID | None, texts: tuple[str, ...] = TEXTS
) -> UUID:
    supplier = make_supplier(cur, ws)
    quote = make_quotation(cur, ws, supplier_id=supplier, status="reviewed")
    for i, text in enumerate(texts, start=1):
        if i == 1:
            line = make_line(cur, ws, quote)
            cur.execute(
                "update quotation_line set original_text=%s,pack_count=null,unit_size=null,"
                "pack_unit=null where id=%s",
                (text, line),
            )
        else:
            cur.execute(
                "insert into quotation_line (tenant_id,quotation_id,line_number,original_text,"
                "quantity,unit_price_amount,unit_price_currency) values (%s,%s,%s,%s,2,12,'GBP')",
                (ws.tenant_id, quote, i * 10, text),
            )
    if rfq_id:
        rec = uuid4()
        cur.execute(
            "insert into rfq_recipient (id,tenant_id,rfq_id,supplier_id,status) "
            "values (%s,%s,%s,%s,'sent')",
            (rec, ws.tenant_id, rfq_id, supplier),
        )
        reset_role(cur)
        cur.execute(
            "insert into rfq_response (tenant_id,rfq_recipient_id,quotation_id) values (%s,%s,%s)",
            (ws.tenant_id, rec, quote),
        )
        act_as(cur, ws)
    return quote


def round_one_product(cur: psycopg.Cursor, ws: Workspace, index: int) -> UUID:
    canonical, product = uuid4(), uuid4()
    reset_role(cur)
    cur.execute(
        "insert into canonical_product (id,name,base_unit) values (%s,%s,%s)",
        (canonical, TEXTS[index], "litre" if index == 1 else "kilogram"),
    )
    act_as(cur, ws)
    cur.execute(
        "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
        "values (%s,%s,%s,%s)",
        (product, ws.tenant_id, canonical, NAMES[index]),
    )
    cur.execute(
        "insert into pack_definition (tenant_id,workspace_product_id,pack_count,unit_size) "
        "values (%s,%s,1,%s)",
        (ws.tenant_id, product, (10, 18, 10, 45)[index]),
    )
    return product


@pytest.mark.parametrize("with_packs", (False, True))
def test_round_one_two_replies_auto_match_without_learning_aliases(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    with_packs: bool,
) -> None:
    enqueued = wire(monkeypatch, conn)
    calls: list[UUID] = []
    original = read_api.rfq_lines_for_quotation

    def counted(settings: Settings, member: CurrentMember, quotation_id: UUID) -> RfqContext | None:
        calls.append(quotation_id)
        return original(settings, member, quotation_id)

    monkeypatch.setattr(matching_module, "rfq_lines_for_quotation", counted, raising=False)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-replay")
        products = [round_one_product(cur, ws, index) for index in range(4)]
        rfq = uuid4()
        act_as(cur, ws)
        cur.execute(
            "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
            "idempotency_key) values (%s,%s,%s,'responded',current_date+7,%s)",
            (rfq, ws.tenant_id, ws.membership_id, uuid4()),
        )
        for i, product in enumerate(products):
            cur.execute(
                "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity,position) "
                "values (%s,%s,%s,8,%s)",
                (ws.tenant_id, rfq, product, i),
            )
        quotes = [reply(cur, ws, rfq), reply(cur, ws, rfq)]
        if with_packs:
            for quote in quotes:
                for line_number, size, unit in (
                    (1, 10, "kilogram"),
                    (20, 18, "litre"),
                    (30, 10, "kilogram"),
                    (40, 45, "kilogram"),
                ):
                    cur.execute(
                        "update quotation_line set pack_count=1,unit_size=%s,pack_unit=%s "
                        "where quotation_id=%s and line_number=%s",
                        (size, unit, quote, line_number),
                    )
    service = MatchingService(settings())
    for quote in quotes:
        result = service.quotation_matches(
            bearer_token="test", member=_member(ws), quotation_id=quote
        )
        assert len(result.lines) == 4
        # The PsycopgTableQuery test double ignores order(); compare by line number.
        by_line = sorted(result.lines, key=lambda row: row.line.line_number)
        assert [row.decision.matched_product.id for row in by_line] == products
        assert all(
            row.decision.is_automatic and row.decision.alias_id is None for row in result.lines
        )
        assert all(row.candidates[0].reasons.rfq.rfq_id == rfq for row in result.lines)
        queue = service.list_match_tasks(
            bearer_token="test", member=_member(ws), quotation_id=quote, status="auto_accepted"
        )
        queued = sorted(queue.items, key=lambda row: row.quotation_line.line_number)
        assert len(queued) == 4
        assert all(row.status == "auto_accepted" for row in queued)
        assert [row.top_candidate.rfq_position for row in queued] == [1, 2, 3, 4]
    with conn.cursor() as cur:
        cur.execute("select count(*) from match_task where status in ('open','in_progress')")
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from product_alias")
        assert cur.fetchone()[0] == 0
        cur.execute("select target from audit_event where action='matching.auto_accepted'")
        targets = [row[0] for row in cur.fetchall()]
        assert len(targets) == 8
        assert all(
            t["reason"] == "rfq_fit"
            and t["rfq_id"] == str(rfq)
            and t["rule_version"] == "rfq-fit-v1"
            for t in targets
        )
    assert enqueued == quotes
    assert calls == quotes
    # Exercise the public responses route with the real RFQ reader/comparison service.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from procurepilot_api.deps import current_member
    from procurepilot_api.modules.rfq.router import router as rfq_router
    from procurepilot_api.modules.rfq.service import RfqService, get_rfq_service

    app = FastAPI()
    app.include_router(rfq_router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _member(ws)
    app.dependency_overrides[get_rfq_service] = lambda: RfqService(settings())
    with TestClient(app) as http:
        response = http.get(f"/api/v1/rfq/{rfq}/responses")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    for item in response.json()["items"]:
        assert [line["workspace_product_id"] for line in item["lines"]] == [
            str(p) for p in products
        ]
        assert all(not line["pending_match"] for line in item["lines"])
    # Reauthorization preserves every existing decision and does not enqueue again.
    for quote in quotes:
        service.quotation_matches(bearer_token="test", member=_member(ws), quotation_id=quote)
    assert enqueued == quotes


def test_no_rfq_preserves_deterministic_alias_matching(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-unprompted")
        product = make_workspace_product(cur, ws, name=NAMES[0])
        quote = reply(cur, ws, None, (TEXTS[0],))
        cur.execute(
            "insert into product_alias (tenant_id,workspace_product_id,alias_text,created_by) "
            "values (%s,%s,%s,%s)",
            (ws.tenant_id, product, TEXTS[0], ws.membership_id),
        )
    result = MatchingService(cast(Settings, settings())).quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    )
    assert result.lines[0].decision.is_automatic
    assert result.lines[0].decision.matched_product.id == product
    assert result.lines[0].candidates[0].reasons.alias_hit
    assert result.lines[0].candidates[0].reasons.rfq is None


def make_rfq(cur: psycopg.Cursor, ws: Workspace, products: list[UUID]) -> UUID:
    rfq = uuid4()
    act_as(cur, ws)
    cur.execute(
        "insert into rfq (id,tenant_id,created_by_membership_id,status,needed_by_date,"
        "idempotency_key) values (%s,%s,%s,'responded',current_date+7,%s)",
        (rfq, ws.tenant_id, ws.membership_id, uuid4()),
    )
    for i, product in enumerate(products):
        cur.execute(
            "insert into rfq_line (tenant_id,rfq_id,workspace_product_id,quantity,position) "
            "values (%s,%s,%s,8,%s)",
            (ws.tenant_id, rfq, product, i),
        )
    return rfq


@pytest.mark.parametrize("fuzzy_enabled", (False, True))
def test_ambiguous_rfq_candidates_lead_and_never_auto_accept(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    fuzzy_enabled: bool,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-ambiguous")
        products = [
            make_workspace_product(cur, ws, name=name) for name in ("زيت دوار الشمس", "زيت ذرة")
        ]
        rfq = make_rfq(cur, ws, products)
        quote = reply(cur, ws, rfq, ("زيت",))
    service = MatchingService(
        settings().model_copy(update={"matching_fuzzy_auto_accept_enabled": fuzzy_enabled})
    )
    result = service.quotation_matches(bearer_token="test", member=_member(ws), quotation_id=quote)
    row = result.lines[0]
    assert row.decision is None
    assert row.task.status == "open"
    assert [c.candidate_product.id for c in row.candidates[:2]] == products
    assert all(c.reasons.rfq.rfq_id == rfq for c in row.candidates[:2])
    assert len({c.candidate_product.id for c in row.candidates}) == len(row.candidates)
    # Existing immutable proposals must also stay in human review on rerun.
    assert (
        service.quotation_matches(bearer_token="test", member=_member(ws), quotation_id=quote)
        .lines[0]
        .decision
        is None
    )


@pytest.mark.parametrize(
    ("quoted_unit", "quoted_size", "pack_check", "quoted_quantity", "quoted_pack_unit"),
    (
        ("litre", 5, "conflict", "5.000000", "litre"),
        ("each", 5, "conflict", "5.000000", "each"),
        ("gram", 5000, "conflict", "5.000000", "kilogram"),
        ("gram", 10000, "equal", "10.000000", "kilogram"),
    ),
)
def test_pack_comparison_remains_visible_with_both_quantities_and_units(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    quoted_unit: str,
    quoted_size: int,
    pack_check: str,
    quoted_quantity: str,
    quoted_pack_unit: str,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-pack-conflict")
        product = round_one_product(cur, ws, 0)
        rfq = make_rfq(cur, ws, [product])
        quote = reply(cur, ws, rfq, (TEXTS[0],))
        cur.execute(
            "update quotation_line set pack_count=1,unit_size=%s,pack_unit=%s "
            "where quotation_id=%s",
            (quoted_size, quoted_unit, quote),
        )
    result = MatchingService(settings()).quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    )
    line = result.lines[0]
    if pack_check == "conflict":
        assert line.decision is None
        assert line.task.status == "open"
    reason = line.candidates[0].reasons.rfq
    assert reason.pack_check == pack_check
    assert reason.quoted_pack_base_quantity == quoted_quantity
    assert reason.rfq_pack_base_quantity == "10.000000"
    assert reason.quoted_pack_unit == quoted_pack_unit
    assert reason.rfq_pack_unit == "kilogram"


@pytest.mark.parametrize("rfq_matched", (True, False, None))
def test_open_queue_uses_only_the_top_candidates_matched_rfq_position(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    rfq_matched: bool | None,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-open-queue")
        product = round_one_product(cur, ws, 0)
        other = round_one_product(cur, ws, 1)
        rfq = make_rfq(cur, ws, [product, other])
        quote = reply(cur, ws, rfq, (TEXTS[0],))
        cur.execute("select id from quotation_line where quotation_id=%s", (quote,))
        line_id = cur.fetchone()[0]
        # Queue projection must also support an RFQ proposal held for human review.
        for rank in (1, 2):
            reasons = {"rfq": {"rfq_id": str(rfq), "position": 7, "matched": True}}
            if rank == 1:
                if rfq_matched is None:
                    reasons = {}
                else:
                    reasons["rfq"]["matched"] = rfq_matched
            cur.execute(
                "insert into match_candidate (tenant_id,quotation_line_id,"
                "candidate_workspace_product_id,confidence,reasons,rank,scoring_version,"
                "embedding_model) values (%s,%s,%s,0.9,%s,%s,'rfq-fit-v1','stub-hash-v1')",
                (
                    ws.tenant_id,
                    line_id,
                    product if rank == 1 else other,
                    psycopg.types.json.Jsonb(reasons),
                    rank,
                ),
            )
        cur.execute(
            "insert into match_task (tenant_id,quotation_line_id,status,priority,reason) "
            "values (%s,%s,'open','normal','low_confidence')",
            (ws.tenant_id, line_id),
        )
    queue = MatchingService(settings()).list_match_tasks(
        bearer_token="test", member=_member(ws), quotation_id=quote, status="open"
    )
    assert len(queue.items) == 1
    assert queue.items[0].status == "open"
    assert queue.items[0].top_candidate.rfq_position == (7 if rfq_matched else None)


def test_rfq_fit_runs_before_a_preexisting_alias_for_another_product(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-before-alias")
        rice = make_workspace_product(cur, ws, name=NAMES[0])
        other = make_workspace_product(cur, ws, name="Old mistaken product")
        rfq = make_rfq(cur, ws, [rice])
        quote = reply(cur, ws, rfq, (TEXTS[0],))
        cur.execute(
            "insert into product_alias (tenant_id,workspace_product_id,alias_text,created_by) "
            "values (%s,%s,%s,%s)",
            (ws.tenant_id, other, TEXTS[0], ws.membership_id),
        )
    result = MatchingService(settings()).quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    )
    assert result.lines[0].decision.matched_product.id == rice
    assert result.lines[0].candidates[0].reasons.rfq.matched
    with conn.cursor() as cur:
        cur.execute("select workspace_product_id from product_alias")
        assert cur.fetchall() == [(other,)]


def test_unrequested_product_keeps_catalogue_match_and_not_in_rfq_evidence(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-extra-line")
        rice = make_workspace_product(cur, ws, name=NAMES[0])
        extra = make_workspace_product(cur, ws, name="طماطم")
        rfq = make_rfq(cur, ws, [rice])
        quote = reply(cur, ws, rfq, ("طماطم",))
    result = MatchingService(settings()).quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    )
    row = result.lines[0]
    assert row.decision is None
    assert row.candidates[0].candidate_product.id == extra
    assert all(c.reasons.rfq.not_in_rfq for c in row.candidates)


def test_archived_rfq_product_is_not_proposed(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-archived")
        rice = make_workspace_product(cur, ws, name=NAMES[0])
        rfq = make_rfq(cur, ws, [rice])
        quote = reply(cur, ws, rfq, (TEXTS[0],))
        cur.execute("update workspace_product set status='archived' where id=%s", (rice,))
    row = (
        MatchingService(settings())
        .quotation_matches(bearer_token="test", member=_member(ws), quotation_id=quote)
        .lines[0]
    )
    assert row.decision is None
    assert not row.candidates


@pytest.mark.parametrize("queue_status", ("all", "auto_accepted", "resolved"))
@pytest.mark.parametrize("new_product", (False, True))
def test_corrected_rfq_auto_match_stays_reachable_and_can_be_corrected_again(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    queue_status: str,
    new_product: bool,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from procurepilot_api.deps import bearer_token, current_member
    from procurepilot_api.errors import register_exception_handlers
    from procurepilot_api.modules.matching import resolution_service as resolution_module
    from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
    from procurepilot_api.modules.matching.router import router
    from procurepilot_api.modules.matching.schemas import MatchCorrectionRequest
    from procurepilot_api.modules.matching.service import get_matching_service

    wire(monkeypatch, conn)
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(resolution_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(resolution_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))
    monkeypatch.setattr(resolution_module, "enqueue_guardrail_evaluation", lambda *_, **__: None)

    @contextmanager
    def scoped(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(resolution_module, "_authenticated_db", scoped)
    monkeypatch.setattr(matching_module, "_authenticated_db", scoped)
    if new_product:
        from procurepilot_api.modules.catalogue import service as catalogue_module

        monkeypatch.setattr(catalogue_module, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(
            catalogue_module,
            "create_client",
            lambda *_: PsycopgSupabaseClient(conn, service_role=True),
        )
        monkeypatch.setattr(catalogue_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))
        monkeypatch.setattr(
            catalogue_module.BillingService,
            "ensure_can_add_active_product",
            lambda *_, **__: None,
        )
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-correct-reopen")
        product = round_one_product(cur, ws, 0)
        other = make_workspace_product(cur, ws, name="Corrected product")
        quote = reply(cur, ws, make_rfq(cur, ws, [product]), (TEXTS[0],))
    matching = MatchingService(settings())
    original = matching.quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    ).lines[0]
    assert original.decision.is_automatic
    assert original.candidates[0].reasons.rfq.matched
    line_id = original.line.id
    candidate_id = uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "insert into match_candidate (id,tenant_id,quotation_line_id,"
            "candidate_workspace_product_id,confidence,reasons,rank,scoring_version,"
            "embedding_model) values (%s,%s,%s,%s,0.9,%s,2,'matching-score-v2','stub-hash-v1')",
            (
                candidate_id,
                ws.tenant_id,
                line_id,
                other,
                psycopg.types.json.Jsonb(
                    {"alias_hit": False, "gtin_match": False, "supplier_code_match": False}
                ),
            ),
        )
    resolution = MatchResolutionService(settings())
    corrected = resolution.correct(
        bearer_token="test",
        member=_member(ws),
        line_id=line_id,
        payload=MatchCorrectionRequest.model_validate(
            {
                "expected_current_decision_id": original.decision.id,
                "learn_alias": False,
                **(
                    {
                        "outcome": "no_match_new_product",
                        "new_product": {
                            "tenant_name": "New corrected product",
                            "base_unit": "kilogram",
                            "pack": {"pack_count": 1, "unit_size": "10"},
                        },
                    }
                    if new_product
                    else {
                        "outcome": "same_product",
                        "selected_match_candidate_id": candidate_id,
                    }
                ),
            }
        ),
        idempotency_key=uuid4(),
    ).decision
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _member(ws)
    app.dependency_overrides[bearer_token] = lambda: "test"
    app.dependency_overrides[get_matching_service] = lambda: matching
    with TestClient(app) as http:
        response = http.get(f"/api/v1/quotation-lines/{line_id}/match-task")
        assert response.status_code == 200, response.text
        task = response.json()
        assert task["decision"]["id"] == str(corrected.id)
        assert task["status"] == "resolved"
        assert task["reason"] == "corrected"
        response = http.get(
            "/api/v1/match-tasks",
            params={
                "quotation_id": str(quote),
                "status": queue_status,
            },
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["quotation_line"]["id"] == str(line_id)
        assert items[0]["status"] == "resolved"
        assert items[0]["reason"] == "corrected"
        assert items[0]["top_candidate"]["rfq_position"] is None
    # The legacy PostgREST queue reader must retain the same current head.
    tasks = matching.list_match_tasks(
        bearer_token="test",
        quotation_id=quote,
        status=queue_status,
    ).items
    assert len(tasks) == 1
    assert tasks[0].decision.id == corrected.id
    assert tasks[0].status == "resolved"
    assert tasks[0].reason == "corrected"
    second = resolution.correct(
        bearer_token="test",
        member=_member(ws),
        line_id=line_id,
        payload=MatchCorrectionRequest(
            expected_current_decision_id=corrected.id,
            outcome="same_product",
            selected_match_candidate_id=original.candidates[0].id,
            learn_alias=False,
        ),
        idempotency_key=uuid4(),
    ).decision
    assert second.supersedes_decision_id == corrected.id
    assert second.matched_product.id == product
    assert (
        matching.match_task_for_line(bearer_token="test", line_id=line_id).decision.id == second.id
    )
    queue = matching.list_match_tasks(
        bearer_token="test", member=_member(ws), quotation_id=quote, status=queue_status
    )
    assert queue.items[0].top_candidate.rfq_position == 1


@pytest.mark.parametrize("learned_alias", (True, False))
def test_rfq_product_keeps_pack_conflict_evidence_for_catalogue_candidates(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    learned_alias: bool,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-alias-pack")
        product = make_workspace_product(cur, ws, name="Flour")
        # The legacy helper's canonical unit is litre; make this a 10 kg flour product.
        reset_role(cur)
        cur.execute(
            "update canonical_product set base_unit='kilogram' where id="
            "(select canonical_product_id from workspace_product where id=%s)",
            (product,),
        )
        act_as(cur, ws)
        cur.execute(
            "update pack_definition set pack_count=1,unit_size=10 where workspace_product_id=%s",
            (product,),
        )
        rfq = make_rfq(cur, ws, [product])
        # A high floor makes the similarity candidate exercise the catalogue fallback as well.
        quote = reply(cur, ws, rfq, ("Flourr",))
        cur.execute(
            "update quotation_line set pack_count=1,unit_size=5,pack_unit='kilogram' "
            "where quotation_id=%s",
            (quote,),
        )
        if learned_alias:
            cur.execute(
                "insert into product_alias (tenant_id,workspace_product_id,alias_text,created_by) "
                "values (%s,%s,'Flourr',%s)",
                (ws.tenant_id, product, ws.membership_id),
            )
    row = (
        MatchingService(settings().model_copy(update={"matching_rfq_fit_floor": 0.9}))
        .quotation_matches(
            bearer_token="test",
            member=_member(ws),
            quotation_id=quote,
        )
        .lines[0]
    )
    candidate = next(c for c in row.candidates if c.candidate_product.id == product)
    reason = candidate.reasons.rfq
    assert reason.not_in_rfq is False
    assert reason.pack_check == "conflict"
    assert reason.quoted_pack_base_quantity == "5.000000"
    assert reason.rfq_pack_base_quantity == "10.000000"
    assert reason.rfq_line_id is not None
    assert candidate.reasons.alias_hit is learned_alias


@pytest.fixture
def correctable_rfq(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> tuple[Workspace, UUID, list[UUID], MatchingService]:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-correction-options", role="buyer")
        products = [
            make_workspace_product(cur, ws, name=name)
            for name in ("Basmati rice", "Basmati grain", "Basmati rice substitute")
        ]
        cur.execute(
            "update pack_definition set unit_size=10 where workspace_product_id=%s",
            (products[1],),
        )
        quote = reply(cur, ws, make_rfq(cur, ws, products[:2]), ("Basmati rice",))
        cur.execute(
            "update quotation_line set pack_count=6,unit_size=5,pack_unit='litre' "
            "where quotation_id=%s",
            (quote,),
        )
    return ws, quote, products, MatchingService(settings())


def test_rfq_auto_match_retains_ranked_rfq_and_similarity_alternatives(
    conn: psycopg.Connection,
    correctable_rfq: tuple[Workspace, UUID, list[UUID], MatchingService],
) -> None:
    from procurepilot_api.modules.matching.search import build_similarity_candidates
    from procurepilot_api.modules.matching.service import _line_row, _line_summary_dict

    ws, quote, products, service = correctable_rfq
    row = service.quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    ).lines[0]
    assert row.decision.is_automatic
    assert len(row.candidates) > 1
    assert [c.candidate_product.id for c in row.candidates[:2]] == products[:2]
    winner, alternative = row.candidates[:2]
    assert winner.rank == 1
    assert winner.confidence == "1.0000"
    assert winner.reasons.rfq.matched is True
    assert row.decision.selected_match_candidate_id == winner.id
    assert alternative.rank == 2
    assert alternative.reasons.rfq.matched is False
    assert alternative.reasons.rfq.pack_check == "conflict"
    assert alternative.scoring_version == "rfq-fit-v1"
    client = PsycopgSupabaseClient(conn)
    similarity = build_similarity_candidates(
        client=client,
        line=_line_summary_dict(_line_row(client, row.line.id)),
        embedding_provider=service._embeddings,
        trigram_threshold=settings().matching_trigram_threshold,
    )
    expected = [c for c in similarity if c.workspace_product_id not in products[:2]]
    assert expected  # Exercise catalogue proposals too, rather than RFQ proposals alone.
    assert [c.candidate_product.id for c in row.candidates[2:]] == [
        c.workspace_product_id for c in expected
    ]
    for actual, searched in zip(row.candidates[2:], expected, strict=True):
        assert actual.confidence == format(searched.confidence, ".4f")
        actual_reasons = actual.reasons.model_dump()
        assert all(actual_reasons[key] == value for key, value in searched.reasons.items())
    assert len({c.candidate_product.id for c in row.candidates}) == len(row.candidates)


def test_buyer_corrects_rfq_auto_match_to_rank_two_existing_product(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    correctable_rfq: tuple[Workspace, UUID, list[UUID], MatchingService],
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from procurepilot_api.deps import bearer_token, current_member
    from procurepilot_api.errors import register_exception_handlers
    from procurepilot_api.modules.matching import resolution_service as resolution_module
    from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
    from procurepilot_api.modules.matching.router import router
    from procurepilot_api.modules.requests.valuation import (
        estimate_from_source_response,
        estimate_line_value,
        quoted_prices_from_source_response,
    )

    ws, quote, products, matching = correctable_rfq
    row = matching.quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    ).lines[0]
    assert len(row.candidates) > 1, (
        "RFQ automatic matches must offer an existing-product correction"
    )
    with conn.cursor() as cur:
        cur.execute("select id from rfq_response where quotation_id=%s", (quote,))
        response_id = cur.fetchone()[0]
    before = estimate_line_value(conn, workspace_product_id=products[0])
    assert (before.unit_price_amount, before.unit_price_currency) == (12, "GBP")
    resolution = MatchResolutionService(settings())
    client = PsycopgSupabaseClient(conn)
    monkeypatch.setattr(resolution_module, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(resolution_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))
    monkeypatch.setattr(resolution_module, "enqueue_guardrail_evaluation", lambda *_, **__: None)

    @contextmanager
    def scoped(*_: object) -> Iterator[psycopg.Connection]:
        yield conn

    monkeypatch.setattr(resolution_module, "_authenticated_db", scoped)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[current_member] = lambda: _member(ws)
    app.dependency_overrides[bearer_token] = lambda: "test"
    app.dependency_overrides[resolution_module.get_match_resolution_service] = lambda: resolution
    with TestClient(app) as http:
        response = http.post(
            f"/api/v1/quotation-lines/{row.line.id}/match/corrections",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_current_decision_id": str(row.decision.id),
                "outcome": "same_product",
                "selected_match_candidate_id": str(row.candidates[1].id),
                "learn_alias": False,
            },
        )
    assert response.status_code == 200, response.text
    corrected = response.json()["decision"]
    assert corrected["id"] != str(row.decision.id)
    assert corrected["supersedes_decision_id"] == str(row.decision.id)
    assert corrected["matched_product"]["id"] == str(products[1])
    assert corrected["is_automatic"] is False
    with conn.cursor() as cur:
        cur.execute(
            "select id from current_match_decision where quotation_line_id=%s", (row.line.id,)
        )
        assert str(cur.fetchone()[0]) == corrected["id"]
        cur.execute(
            "select match_decision_id from landed_cost where quotation_line_id=%s", (row.line.id,)
        )
        assert {str(r[0]) for r in cur.fetchall()} == {str(row.decision.id), corrected["id"]}
        # Corrections must not change the supplier's quoted price/quantity (per purchasing pack).
        cur.execute(
            "select quantity,unit_price_amount,unit_price_currency,pack_count,unit_size "
            "from quotation_line where id=%s",
            (row.line.id,),
        )
        assert cur.fetchone() == (2, 12, "GBP", 6, 5)
    # Requests still use the current decision and a price per purchasing pack, including
    # when sourced from this RFQ response. Historical costs must not price the old product.
    assert estimate_line_value(conn, workspace_product_id=products[0]).unit_price_amount is None
    after = estimate_line_value(conn, workspace_product_id=products[1])
    assert (after.unit_price_amount, after.unit_price_currency) == (12, "GBP")
    assert after.source_landed_cost_id != before.source_landed_cost_id
    assert estimate_from_source_response(
        conn, rfq_response_id=response_id, product_ids=products
    ) == {products[1]: after}
    assert quoted_prices_from_source_response(
        conn, rfq_response_id=response_id, product_ids=products
    ) == {products[1]: (12, "GBP", False, None)}
