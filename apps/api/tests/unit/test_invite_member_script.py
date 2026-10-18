from __future__ import annotations

import argparse
import os
import runpy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from procurepilot_api.modules.members.invitations import hash_member_invitation_token

_SCRIPT = Path(__file__).parents[2] / "scripts" / "invite_member.py"
_MODULE = runpy.run_path(_SCRIPT)
hash_token = _MODULE["hash_token"]
acceptance_url = _MODULE["acceptance_url"]
parse_args = _MODULE["parse_args"]
load_env_file = _MODULE["load_env_file"]
main = _MODULE["main"]


@pytest.fixture
def restore_environ() -> Iterator[None]:
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


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


def test_load_env_file_loads_unset_variables(
    restore_environ: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEST_INVITE_VAR_UNSET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_INVITE_VAR_UNSET=loaded_value\n")

    assert load_env_file(env_file) is True
    assert os.environ.get("TEST_INVITE_VAR_UNSET") == "loaded_value"


def test_load_env_file_does_not_override_exported_variables(
    restore_environ: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_INVITE_VAR_EXISTING", "original_value")
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_INVITE_VAR_EXISTING=new_value\n")

    assert load_env_file(env_file) is True
    assert os.environ.get("TEST_INVITE_VAR_EXISTING") == "original_value"


def test_load_env_file_missing_file_returns_false_and_changes_nothing(
    restore_environ: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_file = tmp_path / "nonexistent.env"
    snapshot_before = dict(os.environ)

    assert load_env_file(missing_file) is False
    assert dict(os.environ) == snapshot_before


def test_main_loads_env_file_and_passes_dsn_and_web_origin_to_run(
    restore_environ: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("WEB_ORIGIN", raising=False)
    monkeypatch.delenv("API_CORS_ORIGINS", raising=False)

    test_dsn = "postgresql://user:secret@localhost:5432/test_db"
    test_origin = "https://app.procurepilot.test"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={test_dsn}\nWEB_ORIGIN={test_origin}\n")

    captured: dict[str, Any] = {}

    def fake_run(args: argparse.Namespace, dsn: str) -> dict[str, Any]:
        captured["args"] = args
        captured["dsn"] = dsn
        return {
            "status": "invited",
            "email": args.email,
            "role": args.role,
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "tenant_name": "Acme Corp",
            "invitation_id": "00000000-0000-0000-0000-000000000002",
            "expires_at": "2026-10-25T00:00:00Z",
            "accept_url": f"{test_origin}/onboarding/accept-invitation?token=xyz",
        }

    monkeypatch.setitem(main.__globals__, "run", fake_run)

    exit_code = main(
        [
            "--owner-email",
            "owner@example.test",
            "--email",
            "invitee@example.test",
            "--env-file",
            str(env_file),
        ]
    )

    assert exit_code == 0
    assert captured["dsn"] == test_dsn
    assert captured["args"].web_origin == test_origin


def test_parse_args_default_env_file_points_at_repo_root() -> None:
    args = parse_args(["--owner-email", "owner@example.test", "--email", "invitee@example.test"])
    repo_root_env = _SCRIPT.resolve().parents[3] / ".env"
    assert args.env_file == repo_root_env
