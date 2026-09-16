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
from procurepilot_api.deps import current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def _app(monkeypatch: pytest.MonkeyPatch, member: object) -> FastAPI:
    app = create_app(settings_for_test_db(monkeypatch))
    app.dependency_overrides[current_member] = lambda: member
    return app


def test_schedule_lifecycle_and_rbac(monkeypatch: pytest.MonkeyPatch) -> None:
    with committed_smart_context("schedule-lifecycle") as context:
        owner_member = member_from_workspace(context.workspace)
        owner_client = TestClient(_app(monkeypatch, owner_member), raise_server_exceptions=False)

        # 1. Create schedule (owner)
        payload = {
            "kind": "savings_ledger",
            "format": "csv",
            "filters": {},
            "weekday": 0,
            "locale": "en",
        }
        res = owner_client.post("/api/v1/reports/schedules", json=payload)
        assert res.status_code == 201, res.text
        created = res.json()
        schedule_id = created["id"]
        assert created["kind"] == "savings_ledger"
        assert created["format"] == "csv"
        assert created["status"] == "active"
        assert created["next_run_at"] is not None

        # 2. Duplicate create is refused with 409
        dup_res = owner_client.post("/api/v1/reports/schedules", json=payload)
        assert dup_res.status_code == 409, dup_res.text

        # 3. Read schedule
        get_res = owner_client.get(f"/api/v1/reports/schedules/{schedule_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == schedule_id

        # 4. List schedules
        list_res = owner_client.get("/api/v1/reports/schedules")
        assert list_res.status_code == 200
        items = list_res.json()["items"]
        assert any(item["id"] == schedule_id for item in items)

        # 5. Pause schedule
        pause_res = owner_client.patch(
            f"/api/v1/reports/schedules/{schedule_id}",
            json={"status": "paused"},
        )
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "paused"

        # 6. Resume schedule
        resume_res = owner_client.patch(
            f"/api/v1/reports/schedules/{schedule_id}",
            json={"status": "active"},
        )
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "active"

        # 7. RBAC: Viewer role cannot update or delete
        viewer_member = context.member.model_copy(update={"role": MemberRole.viewer})
        viewer_client = TestClient(_app(monkeypatch, viewer_member), raise_server_exceptions=False)

        forbidden_patch = viewer_client.patch(
            f"/api/v1/reports/schedules/{schedule_id}",
            json={"status": "paused"},
        )
        assert forbidden_patch.status_code == 403

        forbidden_delete = viewer_client.delete(f"/api/v1/reports/schedules/{schedule_id}")
        assert forbidden_delete.status_code == 403

        # 8. Delete schedule (owner)
        del_res = owner_client.delete(f"/api/v1/reports/schedules/{schedule_id}")
        assert del_res.status_code == 204

        # 9. Verify deleted schedule returns 404
        post_del = owner_client.get(f"/api/v1/reports/schedules/{schedule_id}")
        assert post_del.status_code == 404
