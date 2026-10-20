from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Never

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    connection,
    make_workspace,
    make_workspace_product,
)
from integration.quotation_helpers import PsycopgSupabaseClient, make_extracted_quotation
from integration.test_quotation_audit import _member, _PsycopgAuditWriter
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.modules.landed_cost import service as landed_cost_module
from procurepilot_api.modules.matching import router as matching_router
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.quotations import confirmation_service as confirmation_module
from procurepilot_api.modules.quotations.router import router as quotation_router

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture
def scenario(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    with contextmanager(connection)() as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "confirm-matching")
            fixture = make_extracted_quotation(cur, workspace)
            product_id = make_workspace_product(cur, workspace, name="Tomatoes case 10 kg")
            cur.execute(
                "insert into product_alias "
                "(tenant_id,workspace_product_id,alias_text,created_by) values (%s,%s,%s,%s)",
                (workspace.tenant_id, product_id, "Tomatoes case 10 kg", workspace.membership_id),
            )
        client = PsycopgSupabaseClient(conn)
        writer = _PsycopgAuditWriter(conn)
        for module in (confirmation_module, matching_module, landed_cost_module):
            monkeypatch.setattr(module, "authenticated_client", lambda *_args: client)
        for module in (confirmation_module, matching_module):
            monkeypatch.setattr(module, "get_audit_writer", lambda: writer)
        monkeypatch.setattr(
            matching_module.MatchingService,
            "_service_role_client",
            lambda _self: PsycopgSupabaseClient(conn, service_role=True),
        )

        @contextmanager
        def authenticated_db(*_args: object) -> Iterator[object]:
            yield conn

        monkeypatch.setattr(matching_module, "_authenticated_db", authenticated_db)
        enqueued = []
        monkeypatch.setattr(
            matching_module,
            "enqueue_guardrail_evaluation",
            lambda _settings, **kwargs: enqueued.append(kwargs),
        )
        app = FastAPI()
        app.include_router(quotation_router, prefix="/api/v1")
        app.include_router(matching_router.router, prefix="/api/v1")
        app.dependency_overrides[bearer_token] = lambda: "caller-token"
        app.dependency_overrides[current_member] = lambda: _member(workspace)
        with TestClient(app) as http:
            yield SimpleNamespace(
                conn=conn,
                http=http,
                fixture=fixture,
                workspace=workspace,
                product_id=product_id,
                enqueued=enqueued,
            )


def _confirm(scenario: SimpleNamespace) -> Response:
    response = scenario.http.post(f"/api/v1/quotations/{scenario.fixture.quotation_id}/confirm")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reviewed"
    return response


def _counts(scenario: SimpleNamespace) -> tuple[int, int, int]:
    with scenario.conn.cursor() as cur:
        cur.execute(
            "select (select count(*) from match_candidate where quotation_line_id = %s), "
            "(select count(*) from match_decision where quotation_line_id = %s), "
            "(select count(*) from match_task where quotation_line_id = %s)",
            (scenario.fixture.line_id,) * 3,
        )
        return cur.fetchone()


def test_quotation_confirm_prepares_automatic_matching_and_enqueues_guardrail(
    scenario: SimpleNamespace,
) -> None:
    _confirm(scenario)
    assert _counts(scenario) == (1, 1, 0)
    with scenario.conn.cursor() as cur:
        cur.execute(
            "select is_automatic, matched_workspace_product_id from match_decision "
            "where quotation_line_id = %s",
            (scenario.fixture.line_id,),
        )
        assert cur.fetchone() == (True, scenario.product_id)
    assert scenario.enqueued == [
        {
            "tenant_id": scenario.workspace.tenant_id,
            "quotation_id": scenario.fixture.quotation_id,
        }
    ]


def test_quotation_confirm_ambiguous_line_is_visible_in_match_tasks(
    scenario: SimpleNamespace,
) -> None:
    with scenario.conn.cursor() as cur:
        cur.execute(
            "delete from product_alias where tenant_id = %s", (scenario.workspace.tenant_id,)
        )
        cur.execute(
            "update quotation_line set original_text = 'Tomatoes case' where id = %s",
            (scenario.fixture.line_id,),
        )
    _confirm(scenario)
    response = scenario.http.get(
        "/api/v1/match-tasks",
        params={
            "quotation_id": str(scenario.fixture.quotation_id),
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    task = response.json()["items"][0]
    assert task["status"] == "open"
    assert task["quotation_line"]["id"] == str(scenario.fixture.line_id)
    before = _counts(scenario)
    assert before[0] > 0 and before[1:] == (0, 1)
    response = scenario.http.get(f"/api/v1/quotations/{scenario.fixture.quotation_id}/matches")
    assert response.status_code == 200, response.text
    assert _counts(scenario) == before


def test_quotation_matches_after_confirm_does_not_duplicate_preparation(
    scenario: SimpleNamespace,
) -> None:
    _confirm(scenario)
    before = _counts(scenario)
    assert before == (1, 1, 0)
    for _ in range(2):
        response = scenario.http.get(f"/api/v1/quotations/{scenario.fixture.quotation_id}/matches")
        assert response.status_code == 200, response.text
        assert _counts(scenario) == before
    assert len(scenario.enqueued) == 1


def test_quotation_confirm_matching_failure_is_logged_and_retryable(
    scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = matching_module.MatchingService.quotation_matches
    calls = []

    def fail(_self: object, **kwargs: object) -> Never:
        calls.append(kwargs)
        with scenario.conn.cursor() as cur:
            cur.execute(
                "select status from quotation where id = %s", (scenario.fixture.quotation_id,)
            )
            assert cur.fetchone() == ("reviewed",)
        raise RuntimeError("matching unavailable")

    monkeypatch.setattr(matching_module.MatchingService, "quotation_matches", fail)
    _confirm(scenario)
    assert len(calls) == 1
    assert calls[0]["bearer_token"] == "caller-token"
    assert "Failed to prepare matching" in caplog.text
    assert _counts(scenario) == (0, 0, 0)
    with scenario.conn.cursor() as cur:
        cur.execute("select status from quotation where id = %s", (scenario.fixture.quotation_id,))
        assert cur.fetchone() == ("reviewed",)
    monkeypatch.setattr(matching_module.MatchingService, "quotation_matches", original)
    response = scenario.http.get(f"/api/v1/quotations/{scenario.fixture.quotation_id}/matches")
    assert response.status_code == 200, response.text
    assert _counts(scenario) == (1, 1, 0)
