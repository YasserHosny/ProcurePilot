from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.tenants import router as tenants_router


class _Query:
    def __init__(self, client: _FakeClient, table: str) -> None:
        self.client, self.table, self.op, self.payload = client, table, "select", None

    def select(self, *_: object) -> _Query:
        return self

    def update(self, payload: dict[str, Any]) -> _Query:
        self.op, self.payload = "update", payload
        return self

    def eq(self, *_: object) -> _Query:
        return self

    def limit(self, *_: object) -> _Query:
        return self

    def execute(self) -> SimpleNamespace:
        if self.op == "update":
            self.client.updates.append(self.payload)
            return SimpleNamespace(data=[])
        if self.table == "supported_currency":
            return SimpleNamespace(data=[{"code": "EGP"}] if self.client.supported else [])
        return SimpleNamespace(data=[{"currency": "USD"}])


class _FakeClient:
    def __init__(self, supported: bool = True) -> None:
        self.supported, self.updates, self.rpcs = supported, [], []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> SimpleNamespace:
        self.rpcs.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=1))


def _app(role: MemberRole) -> FastAPI:
    app = create_app()
    app.dependency_overrides[current_member] = lambda: CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=role,
    )
    return app


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    role: MemberRole,
    fake: _FakeClient,
    currency: str,
) -> Response:
    monkeypatch.setattr(tenants_router, "authenticated_client", lambda *_: fake)
    monkeypatch.setattr(
        tenants_router,
        "load_me_for_token",
        lambda **_: SimpleNamespace(
            tenant={
                "id": str(uuid4()),
                "name": "T",
                "slug": "t",
                "region": "EG",
                "currency": "EGP",
                "tax_model": "exclusive",
                "default_locale": "en",
            }
        ),
    )
    with TestClient(_app(role)) as client:
        return client.patch(
            "/api/v1/tenant",
            json={"currency": currency},
            headers={"Authorization": "Bearer t"},
        )


def test_owner_changes_currency_and_audit_event_records_old_and_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient()
    response = _patch(monkeypatch, MemberRole.owner, fake, "EGP")
    assert response.status_code == 200, response.text
    assert fake.updates == [{"currency": "EGP"}]
    ((name, params),) = fake.rpcs
    assert name == "record_audit_event"
    assert params["p_action"] == "tenant.currency_changed"
    assert params["p_target"] == {"from": "USD", "to": "EGP"}


def test_unsupported_currency_is_422_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(supported=False)
    response = _patch(monkeypatch, MemberRole.owner, fake, "ZZZ")
    assert response.status_code == 422
    assert fake.updates == [] and fake.rpcs == []


def test_non_owner_cannot_change_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    response = _patch(monkeypatch, MemberRole.buyer, fake, "EGP")
    assert response.status_code == 403
    assert fake.updates == []
