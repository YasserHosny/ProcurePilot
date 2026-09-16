from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from procurepilot_api.deps import current_member
from procurepilot_api.main import create_app
from procurepilot_api.workers.digest_worker import tick

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    return app


def test_digest_subscription_lifecycle_and_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with committed_smart_context("digest-sub-lifecycle") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        # 1. Create subscription
        payload = {
            "filters": {},
            "locale": "en",
            "channel": "in_app",
        }
        res = client.post("/api/v1/digests/subscriptions", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        sub_id = data["id"]
        assert data["channel"] == "in_app"
        assert data["status"] == "active"
        assert data["locale"] == "en"

        # 2. Duplicate create is refused with 409
        dup_res = client.post("/api/v1/digests/subscriptions", json=payload)
        assert dup_res.status_code == 409, dup_res.text

        # 3. List subscriptions
        list_res = client.get("/api/v1/digests/subscriptions")
        assert list_res.status_code == 200
        items = list_res.json()["items"]
        assert any(i["id"] == sub_id for i in items)

        # 4. Pause subscription
        pause_res = client.patch(
            f"/api/v1/digests/subscriptions/{sub_id}",
            json={"status": "paused"},
        )
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "paused"

        # 5. Resume subscription
        resume_res = client.patch(
            f"/api/v1/digests/subscriptions/{sub_id}",
            json={"status": "active"},
        )
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "active"

        # 6. Delete subscription
        del_res = client.delete(f"/api/v1/digests/subscriptions/{sub_id}")
        assert del_res.status_code == 204


def test_digest_cross_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-negotiable Rule 3: cross-tenant access returns 404, never 403."""
    with (
        committed_smart_context("digest-iso-a") as ctx_a,
        committed_smart_context("digest-iso-b") as ctx_b,
    ):
        member_a = member_from_workspace(ctx_a.workspace)
        member_b = member_from_workspace(ctx_b.workspace)

        client_a = TestClient(_app(monkeypatch, member_a), raise_server_exceptions=False)
        client_b = TestClient(_app(monkeypatch, member_b), raise_server_exceptions=False)

        # Create subscription in Tenant A
        res_a = client_a.post(
            "/api/v1/digests/subscriptions",
            json={"filters": {}, "locale": "en", "channel": "in_app"},
        )
        assert res_a.status_code == 201
        sub_a_id = res_a.json()["id"]

        # Member B attempts to update or delete Tenant A's subscription -> 404
        patch_res = client_b.patch(
            f"/api/v1/digests/subscriptions/{sub_a_id}",
            json={"status": "paused"},
        )
        assert patch_res.status_code == 404

        del_res = client_b.delete(f"/api/v1/digests/subscriptions/{sub_a_id}")
        assert del_res.status_code == 404


def test_latest_digest_content_assembly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: latest digest assembled in strict 5-section order with hero verified savings."""
    with committed_smart_context("digest-latest-view") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        res = client.get("/api/v1/digests/latest")
        assert res.status_code == 200, res.text
        digest = res.json()

        assert "period_start" in digest
        assert "period_end" in digest
        assert "sections" in digest
        sections = digest["sections"]
        assert len(sections) == 5

        expected_order = [
            "verified_savings",
            "pending_verifications",
            "pending_approvals",
            "anomalies",
            "expiring_validity",
        ]
        actual_order = [s["kind"] for s in sections]
        assert actual_order == expected_order


def test_digest_worker_execution_and_skip_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T024 & FR-010: worker claims due subscriptions, handles unconfigured email,

    and skips inactive memberships.
    """
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("digest-worker-run") as context:
        member = member_from_workspace(context.workspace)

        # 1. Create due subscription for in_app channel
        due_time = datetime.now(UTC) - timedelta(minutes=5)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into digest_subscription
                      (tenant_id, membership_id, kind, locale, filters, filters_digest,
                       channel, status, next_run_at)
                    values (%s, %s, 'weekly_digest', 'en', '{}'::jsonb, 'digest_test_1',
                            'in_app', 'active', %s)
                    """,
                    (context.workspace.tenant_id, member.membership_id, due_time),
                )
            conn.commit()

        # Run worker tick
        stats = tick(settings)
        assert stats["claimed"] >= 1
        assert stats["succeeded"] >= 1

        # 2. Test email_unconfigured path when SMTP is unset
        monkeypatch.setattr(settings, "smtp_host", None)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into digest_subscription
                      (tenant_id, membership_id, kind, locale, filters, filters_digest,
                       channel, status, next_run_at)
                    values (%s, %s, 'weekly_digest', 'en', '{}'::jsonb, 'digest_test_2',
                            'email', 'active', %s)
                    """,
                    (context.workspace.tenant_id, member.membership_id, due_time),
                )
            conn.commit()

        stats_email = tick(settings)
        assert stats_email["claimed"] >= 1
        assert stats_email["email_unconfigured"] >= 1

        # 3. Test skip inactive membership
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                # Suspend membership
                cur.execute(
                    "update membership set status = 'suspended' where id = %s",
                    (member.membership_id,),
                )
                # Reset next_run_at to past
                cur.execute(
                    "update digest_subscription set next_run_at = %s where tenant_id = %s",
                    (due_time, context.workspace.tenant_id),
                )
            conn.commit()

        stats_inactive = tick(settings)
        assert stats_inactive["claimed"] >= 1
        assert stats_inactive["skipped"] >= 1
