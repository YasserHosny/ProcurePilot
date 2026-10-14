from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from postgrest.exceptions import APIError

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.tenants import router as tenants_router


class _FakeClient:
    def __init__(self, supported: bool = True) -> None:
        self.supported, self.updates, self.rpcs = supported, [], []

    def table(self, name: str) -> _Table:
        return _Table(self)

    def rpc(self, name: str, params: dict[str, Any]) -> SimpleNamespace:
        self.rpcs.append((name, params))
        if not self.supported:
            error = APIError({"message": "unsupported currency", "code": "22023"})

            def boom() -> None:
                raise error

            return SimpleNamespace(execute=boom)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data="USD"))


class _Table:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client

    def update(self, payload: dict[str, Any]) -> _Table:
        self.client.updates.append(payload)
        return self

    def eq(self, *_: object) -> _Table:
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[])


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
    assert fake.updates == []  # the RPC does the update + audit in one transaction
    ((name, params),) = fake.rpcs
    assert name == "set_tenant_currency"
    assert params["p_currency"] == "EGP"
    assert params["p_actor_email"] == "owner@example.test"


def test_unsupported_currency_is_422_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(supported=False)
    response = _patch(monkeypatch, MemberRole.owner, fake, "ZZZ")
    assert response.status_code == 422
    assert fake.updates == []


def test_non_owner_cannot_change_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    response = _patch(monkeypatch, MemberRole.buyer, fake, "EGP")
    assert response.status_code == 403
    assert fake.rpcs == [] and fake.updates == []
