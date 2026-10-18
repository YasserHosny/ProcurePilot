"""Invite a person into an existing workspace on behalf of one of its owners.

Operator tool: the CLI equivalent of an owner using Team -> Invite in the web app. It writes the
same rows the API's ``MemberInvitationService.issue`` writes — a ``member_invitation`` holding
only the sha256 of the token, plus a ``member.invited`` audit event attributed to the owner — and
prints the acceptance link. The CLI does not email invitations (the web flow does), so the link
must be sent to the invitee by hand; it is shown once and cannot be recovered later (only its
hash is stored).

Run from the repo root with ``DATABASE_URL`` pointing at the target database:

    pnpm db:invite-member --owner-email owner@example.com --email new@example.com --role buyer

If the owner belongs to more than one workspace as owner, pass ``--tenant-id``. If a pending
invitation already exists for the address, pass ``--replace`` to revoke it and issue a new one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row

ROLES = ("owner", "buyer", "branch_manager", "approver", "viewer")
ACCEPT_PATH = "/onboarding/accept-invitation"


def hash_token(token: str) -> str:
    """Must match ``hash_member_invitation_token`` in the members module."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def acceptance_url(web_origin: str, token: str) -> str:
    """Must match the link the web invite dialog builds."""
    return f"{web_origin.rstrip('/')}{ACCEPT_PATH}?token={quote(token, safe='')}"


def default_web_origin() -> str:
    explicit = os.environ.get("WEB_ORIGIN")
    if explicit:
        return explicit
    cors = os.environ.get("API_CORS_ORIGINS", "")
    first = cors.split(",")[0].strip()
    return first or "http://localhost:4200"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner-email", required=True, help="An active owner of the workspace.")
    parser.add_argument("--email", required=True, help="The person to invite.")
    parser.add_argument("--role", choices=ROLES, default="buyer")
    parser.add_argument("--tenant-id", help="Required only if the owner owns several workspaces.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Revoke an existing pending invitation for this address and issue a new one.",
    )
    parser.add_argument("--web-origin", default=None, help="Defaults to WEB_ORIGIN.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args(argv)
    args.email = args.email.strip()
    args.owner_email = args.owner_email.strip()
    if "@" not in args.email or "@" not in args.owner_email:
        parser.error("--email and --owner-email must be email addresses")
    return args


def find_owner(cur: psycopg.Cursor, owner_email: str, tenant_id: str | None) -> dict[str, Any]:
    cur.execute(
        """
        select m.id as membership_id, m.tenant_id, m.email, t.name as tenant_name
        from membership m
        join tenant t on t.id = m.tenant_id
        where lower(m.email) = lower(%s)
          and m.role = 'owner'
          and m.status = 'active'
          and (%s::uuid is null or m.tenant_id = %s::uuid)
        order by t.created_at
        """,
        (owner_email, tenant_id, tenant_id),
    )
    rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"No active owner membership found for {owner_email}.")
    if len(rows) > 1:
        listing = "\n".join(f"  {r['tenant_id']}  {r['tenant_name']}" for r in rows)
        raise SystemExit(
            f"{owner_email} owns several workspaces; pass --tenant-id with one of:\n{listing}"
        )
    return rows[0]


def run(args: argparse.Namespace, dsn: str) -> dict[str, Any]:
    ttl_days = int(os.environ.get("MEMBER_INVITATION_TTL_DAYS", "7"))
    web_origin = args.web_origin or default_web_origin()

    # Simple protocol: Supabase's transaction pooler can hand back stale prepared statements.
    with (
        psycopg.connect(dsn, row_factory=dict_row, prepare_threshold=None) as conn,
        conn.cursor() as cur,
    ):
        owner = find_owner(cur, args.owner_email, args.tenant_id)
        tenant_id = owner["tenant_id"]

        cur.execute(
            """
            select role from membership
            where tenant_id = %s and lower(email) = lower(%s) and status = 'active'
            """,
            (tenant_id, args.email),
        )
        existing_member = cur.fetchone()
        if existing_member is not None:
            return {
                "status": "already_member",
                "tenant_id": str(tenant_id),
                "tenant_name": owner["tenant_name"],
                "email": args.email,
                "role": existing_member["role"],
            }

        cur.execute(
            """
            select id from member_invitation
            where tenant_id = %s and lower(email) = lower(%s) and status = 'pending'
            """,
            (tenant_id, args.email),
        )
        pending = cur.fetchone()
        if pending is not None:
            if not args.replace:
                raise SystemExit(
                    f"{args.email} already has a pending invitation ({pending['id']}). Its link "
                    "cannot be recovered; re-run with --replace to revoke it and issue a new one."
                )
            cur.execute(
                "update member_invitation set status = 'revoked' where id = %s",
                (pending["id"],),
            )
            record_audit(
                cur,
                owner,
                action="member.invitation_revoked",
                target={"invitation_id": str(pending["id"]), "via": "operator_cli"},
            )

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
        cur.execute(
            """
            insert into member_invitation
              (tenant_id, email, role, token_hash, invited_by, expires_at)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                tenant_id,
                args.email,
                args.role,
                hash_token(token),
                owner["membership_id"],
                expires_at,
            ),
        )
        invitation = cur.fetchone()
        record_audit(
            cur,
            owner,
            action="member.invited",
            target={
                "invitation_id": str(invitation["id"]),
                "email": args.email,
                "role": args.role,
                "via": "operator_cli",
            },
        )
        conn.commit()

    return {
        "status": "invited",
        "tenant_id": str(tenant_id),
        "tenant_name": owner["tenant_name"],
        "invitation_id": str(invitation["id"]),
        "email": args.email,
        "role": args.role,
        "expires_at": expires_at.isoformat(),
        "accept_url": acceptance_url(web_origin, token),
    }


def record_audit(
    cur: psycopg.Cursor, owner: dict[str, Any], *, action: str, target: dict[str, str]
) -> None:
    cur.execute(
        """
        insert into audit_event
          (tenant_id, actor_membership_id, actor_email, action, target, outcome)
        values (%s, %s, %s, %s, %s::jsonb, 'success')
        """,
        (owner["tenant_id"], owner["membership_id"], owner["email"], action, json.dumps(target)),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 1

    result = run(args, dsn)
    if args.json:
        print(json.dumps(result))
        return 0
    if result["status"] == "already_member":
        print(
            f"{result['email']} is already an active {result['role']} of "
            f"{result['tenant_name']} ({result['tenant_id']}). Nothing to do."
        )
        return 0
    print(f"Invited {result['email']} as {result['role']} to {result['tenant_name']}.")
    print(f"Expires: {result['expires_at']}")
    print()
    print("Send this link to the invitee (shown once; it is not emailed):")
    print(f"  {result['accept_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
