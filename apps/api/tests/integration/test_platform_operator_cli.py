"""Platform-operator CLI against a real database (spec 025 T060). UNRUN without TEST_DATABASE_URL.

Grant, revoke and list write the table and the audit trail together; revoking twice is quiet;
granting needs an existing user with an active membership.
"""

from __future__ import annotations

import os

import psycopg
import pytest

from integration.feedback_operator_helpers import committed_workspace
from procurepilot_api.workers.platform_operator_cli import main

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


def _row(user_id: object) -> tuple | None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        return conn.execute(
            "select email, granted_by, revoked_at is not null, digest_opt_in "
            "from platform_operator where user_id = %s",
            (user_id,),
        ).fetchone()


def _audit(action: str, email: str) -> list[dict]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        rows = conn.execute(
            "select tenant_id, actor_email, target from audit_event "
            "where action = %s and target ->> 'operator_email' = %s order by id",
            (action, email),
        ).fetchall()
    return [{"tenant_id": r[0], "actor": r[1], "target": r[2]} for r in rows]


def test_grant_makes_an_existing_member_an_operator_and_audits_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with committed_workspace("clig") as ws:
        # The membership e-mail differs from the auth e-mail in the shared fixture; the CLI looks
        # the user up by auth.users.email, which the fixture sets to `{label}-{role}-{hex}@...`.
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            (auth_email,) = conn.execute(
                "select email from auth.users where id = %s", (ws.user_id,)
            ).fetchone()  # type: ignore[misc]

        assert main(["grant", auth_email.upper(), "--granted-by", "tests"]) == 0
        assert f"granted: {auth_email}" in capsys.readouterr().out

        row = _row(ws.user_id)
        assert row == (auth_email, "tests", False, False)
        events = _audit("platform_operator.granted", auth_email)
        assert len(events) == 1
        assert events[0]["actor"] == "tests"
        assert events[0]["tenant_id"] is None


def test_grant_refuses_unknown_users_and_non_members(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["grant", "nobody-at-all@example.test"]) == 1
    assert "no user with email" in capsys.readouterr().err

    with committed_workspace("clinm") as ws:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            conn.execute(
                "update membership set status = 'removed' where user_id = %s", (ws.user_id,)
            )
            (auth_email,) = conn.execute(
                "select email from auth.users where id = %s", (ws.user_id,)
            ).fetchone()  # type: ignore[misc]
        assert main(["grant", auth_email]) == 1
        assert "not an active member" in capsys.readouterr().err
        assert _row(ws.user_id) is None


def test_revoke_is_idempotent_and_audited_once(capsys: pytest.CaptureFixture[str]) -> None:
    with committed_workspace("clir") as ws:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            (auth_email,) = conn.execute(
                "select email from auth.users where id = %s", (ws.user_id,)
            ).fetchone()  # type: ignore[misc]
        assert main(["grant", auth_email, "--granted-by", "tests"]) == 0

        assert main(["revoke", auth_email]) == 0
        assert f"revoked: {auth_email}" in capsys.readouterr().out
        assert _row(ws.user_id)[2] is True  # type: ignore[index]

        assert main(["revoke", auth_email]) == 0
        assert "nothing to do" in capsys.readouterr().out
        assert len(_audit("platform_operator.revoked", auth_email)) == 1


def test_regrant_after_revoke_reactivates_and_keeps_the_digest_preference() -> None:
    with committed_workspace("clire") as ws:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            (auth_email,) = conn.execute(
                "select email from auth.users where id = %s", (ws.user_id,)
            ).fetchone()  # type: ignore[misc]
        assert main(["grant", auth_email, "--granted-by", "tests"]) == 0
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            conn.execute(
                "update platform_operator set digest_opt_in = true where user_id = %s",
                (ws.user_id,),
            )
        assert main(["revoke", auth_email]) == 0
        assert main(["grant", auth_email, "--granted-by", "second"]) == 0
        assert _row(ws.user_id) == (auth_email, "second", False, True)


def test_list_shows_active_operators_and_all_includes_revoked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with committed_workspace("clil") as ws:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            (auth_email,) = conn.execute(
                "select email from auth.users where id = %s", (ws.user_id,)
            ).fetchone()  # type: ignore[misc]
        assert main(["grant", auth_email, "--granted-by", "tests"]) == 0
        capsys.readouterr()

        assert main(["list"]) == 0
        assert auth_email in capsys.readouterr().out

        assert main(["revoke", auth_email]) == 0
        capsys.readouterr()
        assert main(["list"]) == 0
        assert auth_email not in capsys.readouterr().out
        assert main(["list", "--all"]) == 0
        assert auth_email in capsys.readouterr().out
