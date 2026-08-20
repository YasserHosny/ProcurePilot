"""Health check honesty — task T033.

FR-024: healthy means the API *and* its database are reachable. A health check that reports ok
while the database is down lets a broken environment pass as working, which is worse than having
no health check at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from procurepilot_api.main import create_app
from procurepilot_api.modules.health import router as health_router


class _FakeQuery:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    def select(self, *_args: object, **_kwargs: object) -> _FakeQuery:
        return self

    def limit(self, *_args: object, **_kwargs: object) -> _FakeQuery:
        return self

    def execute(self) -> dict[str, object]:
        if self._fail:
            raise ConnectionError("database unreachable")
        return {"data": [{"code": "GB"}]}


class _FakeClient:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self._fail)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_reports_ok_when_the_database_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_router, "_probe_client", lambda _s: _FakeClient(fail=False))
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_reports_unhealthy_when_the_database_is_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_router, "_probe_client", lambda _s: _FakeClient(fail=True))
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["code"]


def test_health_needs_no_authentication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Orchestrators probe this without credentials; requiring a token would defeat it."""
    monkeypatch.setattr(health_router, "_probe_client", lambda _s: _FakeClient(fail=False))
    assert client.get("/api/v1/health").status_code == 200
