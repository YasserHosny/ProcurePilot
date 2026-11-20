"""Platform-operator authentication (spec 025, research D2, ADR-027).

A platform operator is an existing workspace member plus a live row in `platform_operator`. This
module holds the two things that make that safe:

* `current_operator` verifies the JWT, re-resolves the membership (as `current_member` does), then
  asks the database, on EVERY request, whether the caller is an active operator. Revoking an
  operator therefore takes effect on their next request, not when their token expires.
  A `platform_operator` claim on the token, if the auth hook stamped one, is a UI hint only and is
  never read here.
* `operator_connection` opens the operator's database access: the direct-psycopg-with-claims path
  (``set local role feedback_app`` plus synthesised claims), never `service_role`. What an
  operator can reach is whatever the operator RLS policies on the feedback tables grant, so a bug
  in an operator route cannot read quotations or orders.

A caller who is authenticated but not an operator gets a plain 404, the same envelope as a route
that does not exist (CLAUDE.md non-negotiable 3: do not leak existence).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any
from uuid import UUID

import psycopg
from fastapi import Depends
from pydantic import BaseModel

from procurepilot_api import db
from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, resolve_member_from_token
from procurepilot_api.errors import NotFoundError, ServiceUnavailableError
from procurepilot_api.modules.auth.jwt import MemberRole


class CurrentOperator(BaseModel):
    """The verified identity of an active platform operator, as a workspace member."""

    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    role: MemberRole

    def as_member(self) -> CurrentMember:
        return CurrentMember(
            membership_id=self.membership_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            email=self.email,
            role=self.role,
        )


def operator_claims(member: CurrentMember | CurrentOperator) -> dict[str, str]:
    """Claims synthesised for the operator's database session.

    `role` stays `authenticated`: the operator is never granted a Postgres role beyond a member's.
    The operator's reach comes from `is_platform_operator()` in the RLS policies, which looks the
    caller's `sub` up in `platform_operator`, not from anything in these claims.
    """
    return {
        "sub": str(member.user_id),
        "tenant_id": str(member.tenant_id),
        "role": "authenticated",
        "member_role": member.role.value,
    }


@contextmanager
def operator_connection(
    settings: Settings,
    member: CurrentMember | CurrentOperator,
) -> Iterator[psycopg.Connection[Any]]:
    """One transaction as `feedback_app` (migration 20261120000100) with the operator's claims.

    Commits on a clean exit and rolls back on an exception, so a caller can write an audit event
    before leaving the block and have a failed audit undo the change.
    """
    try:
        with db.connect(settings.database_url.get_secret_value()) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role feedback_app")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps(operator_claims(member)),),
                )
            yield conn
    except psycopg.Error as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc


def is_active_operator(settings: Settings, member: CurrentMember) -> bool:
    """The live check: is this caller in `platform_operator` with `revoked_at is null` right now."""
    with operator_connection(settings, member) as conn:
        row = conn.execute("select is_platform_operator()").fetchone()
    return bool(row and row[0])


def current_operator(
    token: Annotated[str, Depends(bearer_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentOperator:
    member = resolve_member_from_token(token, settings)
    if not is_active_operator(settings, member):
        # Deliberately no details: identical to the generic 404 for an unknown route.
        raise NotFoundError()
    return CurrentOperator(
        membership_id=member.membership_id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        email=member.email,
        role=member.role,
    )
