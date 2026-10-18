"""Finding 37: set_tenant_default_locale changes only the caller's own workspace and records
tenant.default_locale_changed in the same transaction, against real Postgres."""

from __future__ import annotations

import json
import os
import sys
import uuid

import psycopg
import pytest

sys.path.append(os.path.dirname(__file__))
from test_rfq_guardrail_management import _seed_tenant  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _as_member(conn: psycopg.Connection, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    claims = {"sub": str(user_id), "tenant_id": str(tenant_id), "role": "authenticated"}
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


def _locale_and_events(tenant_id: uuid.UUID) -> tuple[str, list[dict[str, str]]]:
    locale, rows = _locale_and_audit_rows(tenant_id)
    return locale, [row[0] for row in rows]


def _locale_and_audit_rows(tenant_id: uuid.UUID) -> tuple[str, list[tuple]]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        locale = conn.execute(
            "select default_locale from tenant where id = %s", (tenant_id,)
        ).fetchone()[0]
        rows = conn.execute(
            "select target, actor_membership_id, actor_email from audit_event "
            "where tenant_id = %s and action = 'tenant.default_locale_changed' order by id",
            (tenant_id,),
        ).fetchall()
        return locale, rows


def test_locale_change_is_audited_scoped_and_validated() -> None:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_a, user_a, membership_a, _ = _seed_tenant(cur)
            tenant_b, _, _, _ = _seed_tenant(cur)
        conn.commit()

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        _as_member(conn, tenant_a, user_a)
        old = conn.execute("select set_tenant_default_locale('ar')").fetchone()[0]
        assert old == "en"
        conn.commit()

    # The audit row names the real caller, derived inside the function.
    locale, rows = _locale_and_audit_rows(tenant_a)
    assert locale == "ar"
    assert rows == [
        ({"from": "en", "to": "ar"}, membership_a, f"guardrail-mgmt-{tenant_a}@example.test")
    ]
    # Tenant B's locale is untouched: the function only ever addresses the caller's claim.
    assert _locale_and_events(tenant_b) == ("en", [])

    # Setting the same value again is a no-op, with no second audit event.
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        _as_member(conn, tenant_a, user_a)
        conn.execute("select set_tenant_default_locale('ar')")
        conn.commit()
    assert _locale_and_events(tenant_a) == ("ar", [{"from": "en", "to": "ar"}])

    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        _as_member(conn, tenant_a, user_a)
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            conn.execute("select set_tenant_default_locale('fr')")
    assert _locale_and_events(tenant_a)[0] == "ar"


def test_a_non_owner_calling_the_function_directly_is_refused() -> None:
    """authenticated can reach the function through PostgREST, so it must check the live role
    itself -- including for a member whose token still says owner after a demotion."""
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            tenant_id, _, _, _ = _seed_tenant(cur)
            buyer_user, buyer_membership = uuid.uuid4(), uuid.uuid4()
            buyer_email = f"locale-buyer-{buyer_membership}@example.test"
            cur.execute(
                "insert into auth.users (id,email) values (%s,%s)", (buyer_user, buyer_email)
            )
            cur.execute(
                "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
                "values (%s,%s,%s,%s,'buyer',true)",
                (buyer_membership, tenant_id, buyer_user, buyer_email),
            )
        conn.commit()

    for stale_claim in (None, "owner"):
        with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as conn:
            claims = {"sub": str(buyer_user), "tenant_id": str(tenant_id), "role": "authenticated"}
            if stale_claim:
                claims["member_role"] = stale_claim
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("select set_tenant_default_locale('ar')")

    assert _locale_and_events(tenant_id) == ("en", [])
