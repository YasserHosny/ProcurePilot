"""GET /api/v1/health reports the build's app_version (spec 025, T007/T014).

Feedback submissions snapshot the running version so triage can tell which build a report came
from. The value comes from settings (APP_VERSION, passed as a build arg in the API image), never
from the request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.main import create_app
from procurepilot_api.modules.health import router as health_router


class _Query:
    def select(self, *_a: object, **_k: object) -> _Query:
        return self

    def limit(self, *_a: object, **_k: object) -> _Query:
        return self

    def execute(self) -> dict[str, object]:
        return {"data": [{"code": "GB"}]}


class _Client:
    def table(self, _name: str) -> _Query:
        return _Query()


def _client(monkeypatch: pytest.MonkeyPatch, version: str) -> TestClient:
    monkeypatch.setattr(health_router, "_probe_client", lambda _s: _Client())
    app = create_app()
    settings: Settings = get_settings().model_copy(update={"app_version": version})
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


def test_health_returns_app_version_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, "2026.11.18-abc1234").get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app_version": "2026.11.18-abc1234"}


def test_health_version_needs_no_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, "dev").get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["app_version"] == "dev"
