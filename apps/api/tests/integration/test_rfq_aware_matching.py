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
        assert [row.decision.matched_product.id for row in result.lines] == products
        assert all(
            row.decision.is_automatic and row.decision.alias_id is None for row in result.lines
        )
        assert all(row.candidates[0].reasons.rfq.rfq_id == rfq for row in result.lines)
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


def test_pack_conflict_remains_visible_with_both_quantities(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, conn)
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        ws = make_workspace(cur, "rfq-pack-conflict")
        product = make_workspace_product(cur, ws, name=NAMES[0])
        rfq = make_rfq(cur, ws, [product])
        quote = reply(cur, ws, rfq, (TEXTS[0],))
        cur.execute(
            "update quotation_line set pack_count=1,unit_size=5,pack_unit='litre' "
            "where quotation_id=%s",
            (quote,),
        )
    result = MatchingService(settings()).quotation_matches(
        bearer_token="test", member=_member(ws), quotation_id=quote
    )
    line = result.lines[0]
    assert line.decision is None
    assert line.task.status == "open"
    reason = line.candidates[0].reasons.rfq
    assert reason.pack_check == "conflict"
    assert reason.quoted_pack_base_quantity == "5.000000"
    assert reason.rfq_pack_base_quantity == "30.000000"


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
