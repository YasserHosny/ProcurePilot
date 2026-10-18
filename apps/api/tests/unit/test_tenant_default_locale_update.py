"""Finding 37: PATCH /tenant changes the workspace default locale (the language RFQ emails go out
in) through set_tenant_default_locale, which updates and audits in one transaction."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from postgrest.exceptions import APIError
from test_tenant_currency_update import _app, _FakeClient

from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.tenants import router as tenants_router


def _patch_locale(
    monkeypatch: pytest.MonkeyPatch, role: MemberRole, fake: _FakeClient, body: dict[str, Any]
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
                "default_locale": body.get("default_locale", "en"),
            }
        ),
    )
    with TestClient(_app(role)) as client:
        return client.patch("/api/v1/tenant", json=body, headers={"Authorization": "Bearer t"})


def test_owner_changes_default_locale_through_the_audited_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient()
    response = _patch_locale(monkeypatch, MemberRole.owner, fake, {"default_locale": "ar"})
    assert response.status_code == 200, response.text
    assert fake.updates == []  # no unaudited direct table write
    # Only the locale: the function names the real caller in the audit event itself.
    assert fake.rpcs == [("set_tenant_default_locale", {"p_locale": "ar"})]


def test_unsupported_default_locale_is_rejected_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient()
    response = _patch_locale(monkeypatch, MemberRole.owner, fake, {"default_locale": "fr"})
    assert response.status_code == 422
    assert fake.rpcs == [] and fake.updates == []


def test_non_owner_cannot_change_default_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    response = _patch_locale(monkeypatch, MemberRole.buyer, fake, {"default_locale": "ar"})
    assert response.status_code == 403
    assert fake.rpcs == [] and fake.updates == []


def test_name_and_locale_together_audit_the_locale_and_update_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient()
    response = _patch_locale(
        monkeypatch, MemberRole.owner, fake, {"default_locale": "en", "name": "Sanad"}
    )
    assert response.status_code == 200, response.text
    assert [name for name, _ in fake.rpcs] == ["set_tenant_default_locale"]
    assert fake.updates == [{"name": "Sanad"}]


def test_database_refusal_of_a_non_owner_is_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API's owner check uses the token's role; the function re-checks the live role (a
    member demoted since sign-in) and raises 42501, which must surface as 403, not 500."""
    fake = _FakeClient()

    def refuse(name: str, params: dict[str, Any]) -> SimpleNamespace:
        fake.rpcs.append((name, params))
        error = APIError({"message": "only the workspace owner", "code": "42501"})

        def boom() -> None:
            raise error

        return SimpleNamespace(execute=boom)

    monkeypatch.setattr(fake, "rpc", refuse)
    response = _patch_locale(monkeypatch, MemberRole.owner, fake, {"default_locale": "ar"})
    assert response.status_code == 403
    assert fake.updates == []
