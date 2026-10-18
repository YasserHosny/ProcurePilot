"""The session must distinguish auth user IDs from workspace membership IDs."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members import service


def test_me_exposes_verified_membership_id_separately_from_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.side_effect = [
        SimpleNamespace(
            data=[
                {
                    "id": str(member.tenant_id),
                    "name": "Example",
                    "slug": "example",
                    "region": "EG",
                    "currency": "EGP",
                    "tax_model": "exclusive",
                    "default_locale": "en",
                }
            ]
        ),
        SimpleNamespace(data=[{"preferred_locale": "en", "mfa_enabled": False}]),
    ]
    monkeypatch.setattr(service, "authenticated_client", lambda *_: client)

    me = service.load_me_for_token(get_settings(), "test-token", member)

    assert me.id == member.user_id
    assert me.membership_id == member.membership_id
    assert me.id != me.membership_id
    assert me.model_dump(mode="json")["membership_id"] == str(member.membership_id)
    assert client.table.return_value.select.return_value.eq.call_args_list[1].args == (
        "id",
        str(member.membership_id),
    )
