from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.catalogue.models import PackInput, ProductCreate
from procurepilot_api.modules.catalogue.service import CatalogueService


def test_catalogue_create_checks_plan_limit_before_product_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"gate": 0, "client": 0}

    def fail_gate(self: object, *, member: CurrentMember) -> None:
        called["gate"] += 1
        raise ConflictError(details={"reason": "plan_limit_reached"})

    def fail_if_client_called(*_args: object, **_kwargs: object) -> object:
        called["client"] += 1
        raise AssertionError("product insert path should not run after plan-limit failure")

    monkeypatch.setattr(
        "procurepilot_api.modules.catalogue.service.BillingService.ensure_can_add_active_product",
        fail_gate,
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.catalogue.service.authenticated_client",
        fail_if_client_called,
    )

    with pytest.raises(ConflictError):
        CatalogueService(settings=object()).create_product(
            bearer_token="token",
            member=CurrentMember(
                membership_id=uuid4(),
                tenant_id=uuid4(),
                user_id=uuid4(),
                email="owner@example.test",
                role=MemberRole.owner,
            ),
            payload=ProductCreate(
                tenant_name="Limit product",
                base_unit="litre",
                pack=PackInput(pack_count=1, unit_size="1"),
            ),
        )

    assert called == {"gate": 1, "client": 0}


def test_product_create_rejects_request_tenant_id_bypass() -> None:
    with pytest.raises(ValueError):
        ProductCreate.model_validate(
            {
                "tenant_name": "Injected tenant",
                "base_unit": "litre",
                "pack": {"pack_count": 1, "unit_size": "1"},
                "tenant_id": str(uuid4()),
            }
        )
