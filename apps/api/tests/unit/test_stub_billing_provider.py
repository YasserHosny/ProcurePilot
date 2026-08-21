from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.modules.billing.provider import StubBillingProvider


def test_stub_provider_uses_deterministic_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    captured = {}

    class _Service:
        def __init__(self, *_args: object) -> None:
            return None

        def assign_default_plan(self, *, member: object) -> object:
            captured["member"] = member
            return "account"

    monkeypatch.setattr("procurepilot_api.modules.billing.provider.BillingService", _Service)

    account = StubBillingProvider(settings=object()).assign_default_plan(tenant_id)

    assert account == "account"
    assert str(captured["member"].tenant_id) == str(tenant_id)


def test_no_stripe_dependency_is_imported() -> None:
    import sys

    assert "stripe" not in sys.modules
