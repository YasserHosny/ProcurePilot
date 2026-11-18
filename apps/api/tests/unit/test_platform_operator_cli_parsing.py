"""Argument parsing and email normalisation for the platform-operator CLI (spec 025 T060)."""

from __future__ import annotations

import pytest

from procurepilot_api.workers.platform_operator_cli import (
    build_parser,
    normalise_email,
)


def test_grant_takes_an_email_and_optional_granted_by() -> None:
    args = build_parser().parse_args(["grant", "Ops@Example.test", "--granted-by", "yasser"])
    assert args.command == "grant"
    assert args.email == "Ops@Example.test"
    assert args.granted_by == "yasser"


def test_grant_defaults_granted_by_to_none_so_the_caller_can_resolve_it() -> None:
    assert build_parser().parse_args(["grant", "a@b.test"]).granted_by is None


def test_revoke_takes_an_email() -> None:
    args = build_parser().parse_args(["revoke", "a@b.test"])
    assert (args.command, args.email) == ("revoke", "a@b.test")


def test_list_has_an_all_flag_defaulting_off() -> None:
    assert build_parser().parse_args(["list"]).all is False
    assert build_parser().parse_args(["list", "--all"]).all is True


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_grant_and_revoke_require_an_email() -> None:
    for command in ("grant", "revoke"):
        with pytest.raises(SystemExit):
            build_parser().parse_args([command])


def test_unknown_subcommand_is_refused() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["promote", "a@b.test"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  Ops@Example.TEST ", "ops@example.test"), ("a@b.test", "a@b.test")],
)
def test_normalise_email_trims_and_lowercases(raw: str, expected: str) -> None:
    assert normalise_email(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "no-at-sign", "a@", "@b.test", "a b@c.test"])
def test_normalise_email_rejects_malformed_addresses(bad: str) -> None:
    with pytest.raises(ValueError):
        normalise_email(bad)
