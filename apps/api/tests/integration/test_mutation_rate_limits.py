from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from integration.value_proof_helpers import fetch_export_jobs
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.exports import service as export_service_module
from procurepilot_api.shared.rate_limit import mutation_limiter

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app


def _schedule_count(tenant_id: object) -> int:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from report_schedule where tenant_id = %s", (tenant_id,)
            )
            return int(cur.fetchone()[0])


def _subscription_count(tenant_id: object) -> int:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from digest_subscription where tenant_id = %s", (tenant_id,)
            )
            return int(cur.fetchone()[0])


def _assert_structured_429(response: object) -> None:
    body = response.json()
    assert response.status_code == 429, response.text
    assert body["code"] == "rate_limit.exceeded"
    assert body["trace_id"]


def test_export_create_rate_limit_refuses_without_queueing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035/FR-020: once the per-member export-create limit is hit, the request is refused
    with the structured 429 envelope and no job is queued (no new export_job row)."""
    mutation_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_EXPORT_CREATE", "2/minute")
    with committed_smart_context("rl-export-create") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        monkeypatch.setattr(
            export_service_module, "_enqueue_export_job", lambda *_a, **_k: None
        )
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        payload = {
            "kind": "savings_ledger",
            "format": "xlsx",
            "filters": {"period_start": "2026-01-01", "period_end": "2026-12-31"},
        }
        first = client.post("/api/v1/exports", json=payload)
        second = client.post("/api/v1/exports", json=payload)
        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text

        third = client.post("/api/v1/exports", json=payload)
        _assert_structured_429(third)

        assert len(fetch_export_jobs(context.workspace.tenant_id)) == 2
    mutation_limiter.reset()


def test_schedule_mutation_rate_limit_refuses_without_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035/FR-020: once the per-member schedule-mutation limit is hit, the create is refused
    with the structured 429 envelope and no report_schedule row is created."""
    mutation_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_SCHEDULE_MUTATION", "2/minute")
    with committed_smart_context("rl-schedule-create") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        # Distinct kind/format pairs so each of the first two calls is a genuine create, not a
        # 409 duplicate — the rate limit is evaluated before the handler runs either way, but a
        # test proving "no row created" is clearer when the earlier calls actually succeed.
        first = client.post(
            "/api/v1/reports/schedules",
            json={"kind": "savings_ledger", "format": "csv", "filters": {}, "weekday": 0},
        )
        second = client.post(
            "/api/v1/reports/schedules",
            json={"kind": "savings_ledger", "format": "xlsx", "filters": {}, "weekday": 0},
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

        third = client.post(
            "/api/v1/reports/schedules",
            json={"kind": "alerts_summary", "format": "csv", "filters": {}, "weekday": 0},
        )
        _assert_structured_429(third)

        assert _schedule_count(context.workspace.tenant_id) == 2
    mutation_limiter.reset()


def test_digest_subscription_rate_limit_refuses_without_creating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035/FR-020: once the per-member digest-subscription-mutation limit is hit, the create
    is refused with the structured 429 envelope and no digest_subscription row is created."""
    mutation_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_DIGEST_MUTATION", "2/minute")
    with committed_smart_context("rl-digest-create") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)

        branch_a, branch_b, branch_c = uuid4(), uuid4(), uuid4()
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into branch (id, tenant_id, name)
                    values (%s, %s, 'RL Branch A'), (%s, %s, 'RL Branch B'), (%s, %s, 'RL Branch C')
                    """,
                    (
                        branch_a,
                        context.workspace.tenant_id,
                        branch_b,
                        context.workspace.tenant_id,
                        branch_c,
                        context.workspace.tenant_id,
                    ),
                )
            conn.commit()

        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        first = client.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {"branch_id": str(branch_a)}, "channel": "in_app"},
        )
        second = client.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {"branch_id": str(branch_b)}, "channel": "in_app"},
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

        third = client.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {"branch_id": str(branch_c)}, "channel": "in_app"},
        )
        _assert_structured_429(third)

        assert _subscription_count(context.workspace.tenant_id) == 2
    mutation_limiter.reset()
