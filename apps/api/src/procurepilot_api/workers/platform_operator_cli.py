"""Grant, revoke and list ProcurePilot platform operators (spec 025, research D2).

    python -m procurepilot_api.workers.platform_operator_cli grant ops@example.com
    python -m procurepilot_api.workers.platform_operator_cli revoke ops@example.com
    python -m procurepilot_api.workers.platform_operator_cli list [--all]

There is no grant UI in v1: this is the only way in. It connects over DATABASE_URL, the trusted
server-side connection the workers use (never from a request path), because `platform_operator` has
no client grants. Granting needs an existing user who is an active member of some workspace: the
JWT parser requires a workspace claim, so an operator without a membership could not sign in to the
app anyway. Every change is audited in the same transaction as the change itself
(`platform_operator.granted`, `platform_operator.revoked`), and revoking someone who is not an
active operator is a quiet no-op, so the command is safe to repeat.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api import db
from procurepilot_api.config import get_settings
from procurepilot_api.shared.logging import get_trace_id

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class OperatorCliError(Exception):
    """A refusal the operator running the CLI should read, not a stack trace."""


def normalise_email(raw: str) -> str:
    email = raw.strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise ValueError(f"not a valid email address: {raw!r}")
    return email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="platform_operator_cli",
        description="Grant, revoke and list ProcurePilot platform operators.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    grant = sub.add_parser("grant", help="make an existing workspace member an operator")
    grant.add_argument("email")
    grant.add_argument(
        "--granted-by",
        default=None,
        help="who is granting (default: the OS user running the command)",
    )

    revoke = sub.add_parser("revoke", help="withdraw operator access (idempotent)")
    revoke.add_argument("email")

    listing = sub.add_parser("list", help="show active operators")
    listing.add_argument("--all", action="store_true", help="include revoked operators")
    return parser


def _audit(
    conn: psycopg.Connection[Any],
    *,
    action: str,
    actor: str | None,
    target: dict[str, object],
) -> None:
    """Append an audit event on the SAME connection, so it commits or rolls back with the change."""
    conn.execute(
        "select record_audit_event(%s, 'success'::audit_outcome, null, null, %s, %s::jsonb, %s)",
        (action, actor, Jsonb(target), get_trace_id()),
    )


def grant_operator(conn: psycopg.Connection[Any], *, email: str, granted_by: str) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select id from auth.users where lower(email) = %s", (email,))
        users = cur.fetchall()
        if not users:
            raise OperatorCliError(f"no user with email {email}; they must sign up first")
        if len(users) > 1:
            raise OperatorCliError(f"more than one user has email {email}; resolve it first")
        user_id = users[0]["id"]

        cur.execute(
            "select count(*) as n from membership where user_id = %s and status = 'active'",
            (user_id,),
        )
        row = cur.fetchone()
        if not row or row["n"] == 0:
            raise OperatorCliError(
                f"{email} is not an active member of any workspace; an operator must be a "
                "workspace member first"
            )

        # Re-granting after a revoke reactivates the row and keeps the digest preference.
        cur.execute(
            """
            insert into platform_operator (user_id, email, granted_by)
            values (%s, %s, %s)
            on conflict (user_id) do update
              set email = excluded.email,
                  granted_by = excluded.granted_by,
                  granted_at = now(),
                  revoked_at = null
            returning user_id, email, granted_at, granted_by
            """,
            (user_id, email, granted_by),
        )
        result = cur.fetchone()
    assert result is not None
    _audit(
        conn,
        action="platform_operator.granted",
        actor=granted_by,
        target={"operator_user_id": str(user_id), "operator_email": email},
    )
    return dict(result)


def revoke_operator(conn: psycopg.Connection[Any], *, email: str, revoked_by: str) -> bool:
    """Revoke every active operator row for this email. Returns False when there was none."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "update platform_operator set revoked_at = now() "
            "where lower(email) = %s and revoked_at is null returning user_id",
            (email,),
        )
        revoked = cur.fetchall()
    for row in revoked:
        _audit(
            conn,
            action="platform_operator.revoked",
            actor=revoked_by,
            target={"operator_user_id": str(row["user_id"]), "operator_email": email},
        )
    return bool(revoked)


def list_operators(conn: psycopg.Connection[Any], *, include_revoked: bool) -> list[dict[str, Any]]:
    where = "" if include_revoked else "where revoked_at is null"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select email, granted_at, granted_by, revoked_at, digest_opt_in "  # noqa: S608
            f"from platform_operator {where} order by granted_at, email"
        )
        return list(cur.fetchall())


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    actor = getattr(args, "granted_by", None) or getpass.getuser()
    try:
        with db.connect(get_settings().database_url.get_secret_value()) as conn:
            if args.command == "grant":
                granted = grant_operator(conn, email=normalise_email(args.email), granted_by=actor)
                print(f"granted: {granted['email']} (by {granted['granted_by']})")
            elif args.command == "revoke":
                if revoke_operator(conn, email=normalise_email(args.email), revoked_by=actor):
                    print(f"revoked: {normalise_email(args.email)}")
                else:
                    print(f"nothing to do: {normalise_email(args.email)} is not an active operator")
            else:
                for row in list_operators(conn, include_revoked=args.all):
                    state = "revoked" if row["revoked_at"] else "active"
                    digest = "digest on" if row["digest_opt_in"] else "digest off"
                    print(
                        f"{row['email']}\t{state}\t{digest}\tgranted {row['granted_at']:%Y-%m-%d}"
                    )
    except (OperatorCliError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
