"""current_operator: JWT first, then a LIVE platform_operator check on every request.

The claim on the token is only a UI hint, so a token that says `platform_operator: true` must not
be enough, and a token without the claim must still work for an active operator. Non-operators
get 404, indistinguishable from a route that does not exist. No database needed: the membership
resolution and the live lookup are patched.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import AuthenticationError, NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.auth import operator as operator_module
from procurepilot_api.modules.auth.jwt import MemberRole

MEMBER = CurrentMember(
    membership_id=uuid4(),
    tenant_id=uuid4(),
    user_id=uuid4(),
    email="ops@example.test",
    role=MemberRole.owner,
)


def _patch(monkeypatch: pytest.MonkeyPatch, *, active: bool | Exception) -> list[CurrentMember]:
    checked: list[CurrentMember] = []
    monkeypatch.setattr(operator_module, "resolve_member_from_token", lambda _t, _s: MEMBER)

    def live_check(_settings: object, member: CurrentMember) -> bool:
        checked.append(member)
        if isinstance(active, Exception):
            raise active
        return active

    monkeypatch.setattr(operator_module, "is_active_operator", live_check)
    return checked


def test_active_operator_is_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    checked = _patch(monkeypatch, active=True)
    operator = operator_module.current_operator("token", get_settings())
    assert operator.user_id == MEMBER.user_id
    assert operator.tenant_id == MEMBER.tenant_id
    assert operator.email == MEMBER.email
    assert operator.membership_id == MEMBER.membership_id
    assert checked == [MEMBER]


def test_non_operator_gets_a_plain_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, active=False)
    with pytest.raises(NotFoundError) as raised:
        operator_module.current_operator("token", get_settings())
    # No details that would distinguish it from a missing route.
    assert raised.value.details is None


def test_the_check_runs_on_every_call_so_revocation_is_immediate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"active": True}
    monkeypatch.setattr(operator_module, "resolve_member_from_token", lambda _t, _s: MEMBER)
    monkeypatch.setattr(operator_module, "is_active_operator", lambda _s, _m: state["active"])

    assert operator_module.current_operator("token", get_settings())
    state["active"] = False
    with pytest.raises(NotFoundError):
        operator_module.current_operator("token", get_settings())


def test_bad_token_stays_a_401_and_never_reaches_the_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[object] = []

    def reject(_token: str, _settings: object) -> CurrentMember:
        raise AuthenticationError(details={"reason": "invalid_token"})

    monkeypatch.setattr(operator_module, "resolve_member_from_token", reject)
    monkeypatch.setattr(operator_module, "is_active_operator", lambda *_a: called.append(1) or True)
    with pytest.raises(AuthenticationError):
        operator_module.current_operator("token", get_settings())
    assert called == []


def test_database_failure_fails_closed_as_503_not_as_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, active=ServiceUnavailableError(details={"dependency": "database"}))
    with pytest.raises(ServiceUnavailableError):
        operator_module.current_operator("token", get_settings())


def test_claims_for_the_operator_connection_never_carry_an_elevated_role() -> None:
    claims = operator_module.operator_claims(MEMBER)
    assert claims["role"] == "authenticated"
    assert claims["sub"] == str(MEMBER.user_id)
    assert claims["tenant_id"] == str(MEMBER.tenant_id)
    assert claims["member_role"] == "owner"
    assert "platform_operator" not in claims
