from __future__ import annotations

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
from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[bearer_token] = lambda: "test-token"
    return app


def test_get_before_any_config_exists_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-config-missing") as context:
        member = member_from_workspace(context.workspace)
        client = TestClient(_app(monkeypatch, member), raise_server_exceptions=False)

        res = client.get("/api/v1/tenants/email-config")

        assert res.status_code == 404, res.text


def test_owner_can_create_and_read_config_via_put(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-config-put") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, owner), raise_server_exceptions=False)

        res = client.put(
            "/api/v1/tenants/email-config",
            json={"daily_limit": 250, "spf_dkim_required": True},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["daily_limit"] == 250
        assert body["spf_dkim_required"] is True
        assert body["enabled"] is True
        assert body["forwarding_address"].endswith("@ingest.procurepilot.local")

        get_res = client.get("/api/v1/tenants/email-config")
        assert get_res.status_code == 200
        assert get_res.json()["daily_limit"] == 250


def test_non_owner_cannot_update_config(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-config-rbac") as context:
        buyer = member_from_workspace(context.workspace, role=MemberRole.buyer)
        client = TestClient(_app(monkeypatch, buyer), raise_server_exceptions=False)

        res = client.put("/api/v1/tenants/email-config", json={"daily_limit": 50})

        assert res.status_code == 403, res.text


def test_enable_and_disable_toggle_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-config-toggle") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, owner), raise_server_exceptions=False)

        disable_res = client.post("/api/v1/tenants/email-config/disable")
        assert disable_res.status_code == 200, disable_res.text
        assert disable_res.json()["enabled"] is False

        enable_res = client.post("/api/v1/tenants/email-config/enable")
        assert enable_res.status_code == 200, enable_res.text
        assert enable_res.json()["enabled"] is True


def test_forwarding_address_is_unique_per_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("ingestion-config-unique") as context:
        owner = member_from_workspace(context.workspace, role=MemberRole.owner)
        client = TestClient(_app(monkeypatch, owner), raise_server_exceptions=False)
        client.put("/api/v1/tenants/email-config", json={})

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select forwarding_address, "
                    "(select slug from tenant where id = %s) as slug "
                    "from tenant_email_config where tenant_id = %s",
                    (context.workspace.tenant_id, context.workspace.tenant_id),
                )
                address, slug = cur.fetchone()

        assert address == f"{slug}@ingest.procurepilot.local"
