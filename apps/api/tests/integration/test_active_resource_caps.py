from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    committed_smart_context,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
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


def test_active_schedule_cap_refuses_a_second_active_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035/FR-020: the count of a member's own *active* schedules is capped independently of
    the request-rate limit — a member can't accumulate unbounded standing recurring jobs even
    spaced well apart in time."""
    mutation_limiter.reset()
    monkeypatch.setenv("ACTIVE_SCHEDULE_CAP_PER_MEMBER", "1")
    with committed_smart_context("cap-schedule") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        first = client.post(
            "/api/v1/reports/schedules",
            json={"kind": "savings_ledger", "format": "csv", "filters": {}, "weekday": 0},
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/reports/schedules",
            json={"kind": "savings_ledger", "format": "xlsx", "filters": {}, "weekday": 0},
        )
        assert second.status_code == 422, second.text
        body = second.json()
        assert body["code"] == "report_schedule_cap_exceeded"
        assert body["details"] == {"cap": 1, "actual": 1}
    mutation_limiter.reset()


def test_active_digest_subscription_cap_refuses_a_second_active_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035/FR-020: same cap discipline for digest subscriptions."""
    mutation_limiter.reset()
    monkeypatch.setenv("ACTIVE_DIGEST_SUBSCRIPTION_CAP_PER_MEMBER", "1")
    with committed_smart_context("cap-digest") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        first = client.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {}, "channel": "in_app"},
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {}, "channel": "email"},
        )
        assert second.status_code == 422, second.text
        body = second.json()
        assert body["code"] == "digest_subscription_cap_exceeded"
        assert body["details"] == {"cap": 1, "actual": 1}
    mutation_limiter.reset()
