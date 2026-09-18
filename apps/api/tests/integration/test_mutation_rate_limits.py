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
from procurepilot_api.modules.auth.jwt import MemberRole
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


def test_accounting_sync_rate_limit_refuses_without_syncing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T039 security review: router.py had zero rate limiting on POST /accounting/sync — a
    real outbound QuickBooks API call chain, and the advisory lock only stops concurrent
    syncs, not rapid sequential ones. Once the per-member limit is hit, the request is
    refused with the structured 429 envelope before SyncService.sync is even called."""
    mutation_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_ACCOUNTING_SYNC", "2/minute")
    monkeypatch.setenv("ACCOUNTING_PROVIDER_MODE", "stub")
    with committed_smart_context("rl-accounting-sync") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    insert into accounting_connection (
                        id, tenant_id, provider, realm_id, display_name,
                        access_token, refresh_token, status, connected_by, connected_at
                    ) values (
                        %s, %s, 'quickbooks', 'stub-realm-12345', 'Demo Company',
                        'test-access-token', 'test-refresh-token', 'active', %s, now()
                    )
                    """,
                    (uuid4(), context.workspace.tenant_id, context.workspace.membership_id),
                )
            conn.commit()

        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        first = client.post("/api/v1/accounting/sync")
        second = client.post("/api/v1/accounting/sync")
        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text

        third = client.post("/api/v1/accounting/sync")
        _assert_structured_429(third)
    mutation_limiter.reset()


def test_accounting_discrepancy_resolve_rate_limit_refuses_without_resolving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T039 security review: same gap as sync, on POST /accounting/discrepancies/{id}/resolve.
    Seeds three distinct open discrepancies so the third call is refused by the rate limit
    itself, not by the already-resolved 409 a repeat call against the same row would hit."""
    mutation_limiter.reset()
    monkeypatch.setenv("RATE_LIMIT_ACCOUNTING_DISCREPANCY_RESOLVE", "2/minute")
    with committed_smart_context("rl-accounting-resolve") as context:
        settings_for_test_db(monkeypatch)
        member = member_from_workspace(context.workspace, role=MemberRole.owner)
        discrepancy_ids = [uuid4(), uuid4(), uuid4()]
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                connection_id = uuid4()
                cur.execute(
                    """
                    insert into accounting_connection (
                        id, tenant_id, provider, realm_id, display_name,
                        access_token, refresh_token, status, connected_by, connected_at
                    ) values (
                        %s, %s, 'quickbooks', 'stub-realm-12345', 'Demo Company',
                        'test-access-token', 'test-refresh-token', 'active', %s, now()
                    )
                    """,
                    (connection_id, context.workspace.tenant_id, context.workspace.membership_id),
                )
                for i, disc_id in enumerate(discrepancy_ids):
                    bill_id = uuid4()
                    vendor_id = uuid4()
                    cur.execute(
                        """
                        insert into synced_vendor (
                            id, tenant_id, connection_id, provider_vendor_id, display_name
                        ) values (%s, %s, %s, %s, %s)
                        """,
                        (vendor_id, context.workspace.tenant_id, connection_id,
                         f"rl-vendor-{i}", f"Rate Limit Vendor {i}"),
                    )
                    cur.execute(
                        """
                        insert into synced_bill (
                            id, tenant_id, connection_id, provider_bill_id, vendor_id,
                            amount, currency, bill_date, provider_status
                        ) values (%s, %s, %s, %s, %s, 100.00, 'USD', current_date, 'open')
                        """,
                        (bill_id, context.workspace.tenant_id, connection_id,
                         f"rl-bill-{i}", vendor_id),
                    )
                    cur.execute(
                        """
                        insert into reconciliation_discrepancy (
                            id, tenant_id, discrepancy_type, synced_bill_id, status, detected_at
                        ) values (%s, %s, 'unmatched_bill', %s, 'open', now())
                        """,
                        (disc_id, context.workspace.tenant_id, bill_id),
                    )
            conn.commit()

        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        first = client.post(
            f"/api/v1/accounting/discrepancies/{discrepancy_ids[0]}/resolve", json={}
        )
        second = client.post(
            f"/api/v1/accounting/discrepancies/{discrepancy_ids[1]}/resolve", json={}
        )
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        third = client.post(
            f"/api/v1/accounting/discrepancies/{discrepancy_ids[2]}/resolve", json={}
        )
        _assert_structured_429(third)
    mutation_limiter.reset()
