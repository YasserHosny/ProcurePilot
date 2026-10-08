from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from procurepilot_api.modules.members.invitations import hash_member_invitation_token

_SCRIPT = Path(__file__).parents[2] / "scripts" / "invite_member.py"
_MODULE = runpy.run_path(_SCRIPT)
hash_token = _MODULE["hash_token"]
acceptance_url = _MODULE["acceptance_url"]
parse_args = _MODULE["parse_args"]


def test_token_hash_matches_the_api_so_the_link_is_acceptable() -> None:
    token = "a" * 43
    assert hash_token(token) == hash_member_invitation_token(token)


def test_acceptance_url_matches_the_web_invite_dialog() -> None:
    assert (
        acceptance_url("https://app.example.test/", "abc-_+/=")
        == "https://app.example.test/onboarding/accept-invitation?token=abc-_%2B%2F%3D"
    )


def test_role_defaults_to_buyer_and_emails_are_trimmed() -> None:
    args = parse_args(["--owner-email", " o@example.test ", "--email", "n@example.test "])
    assert (args.owner_email, args.email, args.role) == (
        "o@example.test",
        "n@example.test",
        "buyer",
    )


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            ["--owner-email", "o@example.test", "--email", "n@example.test", "--role", "god"]
        )
