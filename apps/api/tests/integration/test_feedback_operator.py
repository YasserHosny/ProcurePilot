"""Platform-operator boundaries for feedback (spec 025 T059, US5, ADR-027). The highest-risk story.

Part 1 runs inside one rolled-back transaction as the real `authenticated` role and proves what the
DATABASE allows an operator to do: read feedback in every workspace, change status and labels
(forward only), and nothing else. Part 2 drives the HTTP routes with committed rows and proves the
API layer: non-operators get 404, revocation bites on the next request, and every operator access
is audited under the right tenant.

The JWT step is patched (a unit test covers it; PostgREST is not part of this suite). The live
`platform_operator` check is NOT patched: it runs against the database on every request.

Set TEST_DATABASE_URL to a database with the migrations applied; skipped otherwise. UNRUN in the
builder environment that wrote it: no database was available.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from integration.feedback_operator_helpers import (
    Workspace,
    act_as,
    committed_workspace,
    grant_operator,
    insert_attachment,
    insert_submission,
    make_workspace,
    operator_member,
)
from procurepilot_api import db
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth import operator as operator_module
from procurepilot_api.modules.feedback.operator_service import (
    OperatorFeedbackService,
    get_operator_feedback_service,
)
from procurepilot_api.shared.audit import AuditEventCreate, AuditWriter

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        yield connection
        connection.rollback()


# ---------------------------------------------------------------------------
# Part 1: what the database lets an operator do
# ---------------------------------------------------------------------------


def _three_workspaces(cur: psycopg.Cursor) -> tuple[Workspace, Workspace, Workspace]:
    operator_home = make_workspace(cur, "opshome")
    other = make_workspace(cur, "opsother")
    bystander = make_workspace(cur, "opsbystander")
    grant_operator(cur, operator_home)
    return operator_home, other, bystander


def test_operator_reads_feedback_from_every_workspace(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, bystander = _three_workspaces(cur)
        own = insert_submission(cur, home)
        foreign = insert_submission(cur, other)
        also_foreign = insert_submission(cur, bystander)
        act_as(cur, home)
        cur.execute("select id from feedback_submission")
        seen = {row[0] for row in cur.fetchall()}
    assert {own, foreign, also_foreign} <= seen


def test_operator_sees_attachments_of_other_workspaces(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        submission = insert_submission(cur, other)
        attachment_id, _ = insert_attachment(cur, other, submission)
        act_as(cur, home)
        cur.execute("select id from feedback_attachment where submission_id = %s", (submission,))
        assert cur.fetchall() == [(attachment_id,)]


def test_a_plain_member_still_sees_only_their_own_workspace(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, bystander = _three_workspaces(cur)
        insert_submission(cur, home)
        theirs = insert_submission(cur, bystander)
        act_as(cur, other)
        cur.execute("select id from feedback_submission where id = %s", (theirs,))
        assert cur.fetchall() == []


def test_operator_cannot_read_any_other_tenant_table(conn: psycopg.Connection) -> None:
    """The exception is confined to the feedback tables: other tenants' data stays invisible."""
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        cur.execute("reset role")
        supplier_id = uuid4()
        cur.execute(
            "insert into supplier (id, tenant_id, name) values (%s, %s, 'Other Co')",
            (supplier_id, other.tenant_id),
        )
        act_as(cur, home)
        for query, params in (
            ("select id from supplier where id = %s", (supplier_id,)),
            ("select id from membership where tenant_id = %s", (other.tenant_id,)),
            ("select id from audit_event where tenant_id = %s", (other.tenant_id,)),
            ("select id from tenant where id = %s", (other.tenant_id,)),
        ):
            cur.execute(query, params)
            assert cur.fetchall() == [], query


def test_platform_operator_table_is_unreachable_by_clients(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, _, _ = _three_workspaces(cur)
        act_as(cur, home)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select * from platform_operator")


def test_operator_updates_status_and_labels_only(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        submission = insert_submission(cur, other)
        act_as(cur, home)
        cur.execute(
            "update feedback_submission set status = 'reviewed', labels = %s where id = %s",
            (["billing", "ui"], submission),
        )
        assert cur.rowcount == 1
        cur.execute(
            "select status::text, feedback_operator_labels(id), status_changed_by "
            "from feedback_submission where id = %s",
            (submission,),
        )
        status, labels, changed_by = cur.fetchone() or (None, None, None)
        assert (status, labels) == ("reviewed", ["billing", "ui"])
        assert changed_by == home.user_id


def test_operator_cannot_edit_the_content_or_context_columns(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        submission = insert_submission(cur, other)
        act_as(cur, home)
        for column, value in (
            ("text_content", "rewritten"),
            ("submitter_email", "someone@else.test"),
            ("tenant_id", str(home.tenant_id)),
        ):
            # A savepoint per attempt: a refused statement aborts only its own sub-transaction.
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    cur.execute(
                        f"update feedback_submission set {column} = %s where id = %s",  # noqa: S608
                        (value, submission),
                    )


def test_a_backward_status_move_is_refused_by_the_trigger(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        submission = insert_submission(cur, other, status="resolved")
        act_as(cur, home)
        with pytest.raises((psycopg.errors.RaiseException, psycopg.errors.CheckViolation)):
            cur.execute(
                "update feedback_submission set status = 'new' where id = %s", (submission,)
            )


def test_operator_cannot_insert_into_another_workspace_or_delete_anything(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        submission = insert_submission(cur, other)
        act_as(cur, home)
        # Delete: the only delete policy is own-and-new, so another workspace's row is untouched.
        cur.execute("delete from feedback_submission where id = %s", (submission,))
        assert cur.rowcount == 0
        cur.execute("reset role")
        cur.execute("select count(*) from feedback_submission where id = %s", (submission,))
        assert cur.fetchone() == (1,)
        # Insert: member policy requires the caller's own tenant and identity.
        act_as(cur, home)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                """
                insert into feedback_submission (
                  tenant_id, submitter_user_id, submitter_name, submitter_email, member_role,
                  text_content, page_path, app_version, locale, is_demo, idempotency_key
                ) values (
                  %s, %s, 'x', 'x@example.test', 'owner', 'forged', '/', 'v', 'en', false, %s
                )
                """,
                (other.tenant_id, home.user_id, uuid4()),
            )


def test_revoking_takes_effect_immediately_at_the_database(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, _ = _three_workspaces(cur)
        foreign = insert_submission(cur, other)
        act_as(cur, home)
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (True,)
        cur.execute("reset role")
        cur.execute(
            "update platform_operator set revoked_at = now() where user_id = %s", (home.user_id,)
        )
        act_as(cur, home)
        cur.execute("select is_platform_operator()")
        assert cur.fetchone() == (False,)
        cur.execute("select id from feedback_submission where id = %s", (foreign,))
        assert cur.fetchall() == []
        # The digest preference is the caller's own row, and only while active.
        cur.execute("select * from operator_digest_preference()")
        assert cur.fetchall() == []
        cur.execute("select * from set_operator_digest_preference(true, null)")
        assert cur.fetchall() == []


def test_digest_preference_functions_touch_only_the_callers_own_row(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        home, other, bystander = _three_workspaces(cur)
        grant_operator(cur, other)
        act_as(cur, home)
        cur.execute(
            "select digest_opt_in, digest_locale from set_operator_digest_preference(true, 'ar')"
        )
        assert cur.fetchone() == (True, "ar")
        cur.execute("reset role")
        cur.execute(
            "select digest_opt_in from platform_operator where user_id = %s", (other.user_id,)
        )
        assert cur.fetchone() == (False,)
        # A member who is not an operator gets nothing and changes nothing.
        act_as(cur, bystander)
        cur.execute("select * from set_operator_digest_preference(true, 'en')")
        assert cur.fetchall() == []
        act_as(cur, home)
        with pytest.raises(psycopg.errors.InvalidParameterValue):
            with conn.transaction():
                cur.execute("select * from set_operator_digest_preference(true, 'fr')")


def test_enabling_the_digest_starts_the_watermark_at_now(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, _, _ = _three_workspaces(cur)
        act_as(cur, home)
        cur.execute("select * from set_operator_digest_preference(true, null)")
        cur.execute("reset role")
        cur.execute(
            "select digest_last_sent_at is not null from platform_operator where user_id = %s",
            (home.user_id,),
        )
        assert cur.fetchone() == (True,)


def test_workspace_names_are_visible_to_operators_only(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        home, other, bystander = _three_workspaces(cur)
        act_as(cur, home)
        cur.execute(
            "select tenant_name from operator_tenant_names(%s::uuid[])", ([other.tenant_id],)
        )
        assert cur.fetchall() == [(f"{other.label} Ltd",)]
        act_as(cur, bystander)
        cur.execute(
            "select tenant_name from operator_tenant_names(%s::uuid[])", ([other.tenant_id],)
        )
        assert cur.fetchall() == []


# ---------------------------------------------------------------------------
# Part 2: the HTTP routes
# ---------------------------------------------------------------------------


class DbAuditWriter(AuditWriter):
    """Writes through `record_audit_event` over DATABASE_URL, so the suite needs no PostgREST."""

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        with db.connect(TEST_DATABASE_URL) as connection:
            connection.execute(
                "select record_audit_event(%s, %s::audit_outcome, %s::uuid, %s::uuid, %s, "
                "%s::jsonb, %s)",
                (
                    event.action,
                    event.outcome,
                    str(event.tenant_id) if event.tenant_id else None,
                    str(event.actor_membership_id) if event.actor_membership_id else None,
                    event.actor_email,
                    Jsonb(event.target) if event.target is not None else None,
                    "test-trace",
                ),
            )


class FakeSigner:
    def sign(self, *, bucket: str, path: str, expires_in: int) -> str:
        return f"https://storage.example.test/{bucket}/{path}?ttl={expires_in}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    identities: dict[str, Workspace] = {}

    def fake_resolve(token: str, _settings: object) -> object:
        return operator_member(identities[token])

    monkeypatch.setattr(operator_module, "resolve_member_from_token", fake_resolve)
    app = create_app()
    app.dependency_overrides[get_operator_feedback_service] = lambda: OperatorFeedbackService(
        audit_writer=DbAuditWriter(), signer=FakeSigner()
    )
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.identities = identities  # type: ignore[attr-defined]
    yield test_client


def _as(client: TestClient, workspace: Workspace) -> dict[str, str]:
    token = f"token-{workspace.user_id}"
    client.identities[token] = workspace  # type: ignore[attr-defined]
    return {"Authorization": f"Bearer {token}"}


def _audit_rows(action: str, *, actor_email: str) -> list[tuple[UUID | None, dict[str, object]]]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        return list(
            connection.execute(
                "select tenant_id, target from audit_event where action = %s and actor_email = %s "
                "order by id",
                (action, actor_email),
            ).fetchall()
        )


def _seed(*, operator: Workspace, other: Workspace) -> tuple[UUID, UUID]:
    with psycopg.connect(TEST_DATABASE_URL or "") as connection:
        with connection.cursor() as cur:
            grant_operator(cur, operator)
            submission = insert_submission(cur, other, text="the compare page hangs")
            attachment, _ = insert_attachment(cur, other, submission)
        connection.commit()
    return submission, attachment


def test_non_operator_gets_404_on_every_platform_route(client: TestClient) -> None:
    with committed_workspace("httpmember") as member, committed_workspace("httpother") as other:
        with psycopg.connect(TEST_DATABASE_URL or "") as connection:
            with connection.cursor() as cur:
                submission = insert_submission(cur, other)
            connection.commit()
        headers = _as(client, member)
        some_id = uuid4()
        calls = [
            client.get("/api/v1/platform/feedback", headers=headers),
            client.get("/api/v1/platform/feedback/me", headers=headers),
            client.put(
                "/api/v1/platform/feedback/digest-preference",
                json={"enabled": True},
                headers=headers,
            ),
            client.get(f"/api/v1/platform/feedback/{submission}", headers=headers),
            client.patch(
                f"/api/v1/platform/feedback/{submission}",
                json={"status": "reviewed"},
                headers=headers,
            ),
            client.get(
                f"/api/v1/platform/feedback/{submission}/attachments/{some_id}/url", headers=headers
            ),
        ]
        for response in calls:
            assert response.status_code == 404, response.request.url
            assert response.json()["code"] == "not_found"
            assert response.json().get("details") is None


def test_operator_lists_filters_and_is_audited_once(client: TestClient) -> None:
    with committed_workspace("httpop") as operator, committed_workspace("httpsrc") as other:
        submission, _ = _seed(operator=operator, other=other)
        headers = _as(client, operator)
        email = operator_member(operator).email  # type: ignore[attr-defined]
        before = len(_audit_rows("feedback.operator_listed", actor_email=email))

        response = client.get(
            "/api/v1/platform/feedback",
            params={"status": "new", "category": "bug", "tenant_id": str(other.tenant_id)},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert [item["id"] for item in items] == [str(submission)]
        assert items[0]["tenant_name"] == f"{other.label} Ltd"
        assert items[0]["submitter_email"].endswith("@example.test")
        assert len(items[0]["attachments"]) == 1

        rows = _audit_rows("feedback.operator_listed", actor_email=email)
        assert len(rows) == before + 1, "one aggregate event per list request, not one per row"
        tenant_id, target = rows[-1]
        assert tenant_id is None
        assert target["result_count"] == 1


def test_list_paginates_with_a_cursor(client: TestClient) -> None:
    with committed_workspace("httppgop") as operator, committed_workspace("httppgsrc") as other:
        with psycopg.connect(TEST_DATABASE_URL or "") as connection:
            with connection.cursor() as cur:
                grant_operator(cur, operator)
                created = [insert_submission(cur, other, text=f"item {n}") for n in range(3)]
            connection.commit()
        headers = _as(client, operator)
        first = client.get(
            "/api/v1/platform/feedback",
            params={"limit": 2, "tenant_id": str(other.tenant_id)},
            headers=headers,
        ).json()
        assert len(first["items"]) == 2 and first["next_cursor"]
        second = client.get(
            "/api/v1/platform/feedback",
            params={"limit": 2, "cursor": first["next_cursor"], "tenant_id": str(other.tenant_id)},
            headers=headers,
        ).json()
        assert len(second["items"]) == 1 and second["next_cursor"] is None
        seen = [item["id"] for item in first["items"] + second["items"]]
        assert sorted(seen) == sorted(str(i) for i in created)
        bad = client.get(
            "/api/v1/platform/feedback", params={"cursor": "not-a-cursor"}, headers=headers
        )
        assert bad.status_code == 422


def test_detail_is_audited_under_the_submissions_tenant(client: TestClient) -> None:
    with committed_workspace("httpdetop") as operator, committed_workspace("httpdetsrc") as other:
        submission, _ = _seed(operator=operator, other=other)
        headers = _as(client, operator)
        email = operator_member(operator).email  # type: ignore[attr-defined]

        response = client.get(f"/api/v1/platform/feedback/{submission}", headers=headers)
        assert response.status_code == 200
        assert response.json()["submitter_name"] == f"{other.label} Submitter"

        tenant_id, target = _audit_rows("feedback.operator_viewed", actor_email=email)[-1]
        assert tenant_id == other.tenant_id
        assert target == {"submission_id": str(submission)}
        assert (
            client.get(f"/api/v1/platform/feedback/{uuid4()}", headers=headers).status_code == 404
        )


def test_status_moves_forward_only_and_is_audited(client: TestClient) -> None:
    with committed_workspace("httpstop") as operator, committed_workspace("httpstsrc") as other:
        submission, _ = _seed(operator=operator, other=other)
        headers = _as(client, operator)
        email = operator_member(operator).email  # type: ignore[attr-defined]
        url = f"/api/v1/platform/feedback/{submission}"

        done = client.patch(url, json={"status": "resolved"}, headers=headers)
        assert done.status_code == 200 and done.json()["status"] == "resolved"
        backwards = client.patch(url, json={"status": "new"}, headers=headers)
        assert backwards.status_code == 409
        assert backwards.json()["code"] == "feedback.invalid_transition"

        tenant_id, target = _audit_rows("feedback.operator_status_changed", actor_email=email)[-1]
        assert tenant_id == other.tenant_id
        assert target == {"submission_id": str(submission), "from": "new", "to": "resolved"}


def test_labels_are_validated_stored_and_kept_out_of_the_audit_trail(client: TestClient) -> None:
    with committed_workspace("httplbop") as operator, committed_workspace("httplbsrc") as other:
        submission, _ = _seed(operator=operator, other=other)
        headers = _as(client, operator)
        email = operator_member(operator).email  # type: ignore[attr-defined]
        url = f"/api/v1/platform/feedback/{submission}"

        ok = client.patch(url, json={"labels": ["billing", " ui "]}, headers=headers)
        assert ok.status_code == 200 and ok.json()["labels"] == ["billing", "ui"]
        assert (
            client.patch(
                url, json={"labels": [f"l{n}" for n in range(11)]}, headers=headers
            ).status_code
            == 422
        )
        assert client.patch(url, json={"labels": ["x" * 41]}, headers=headers).status_code == 422
        assert client.patch(url, json={}, headers=headers).status_code == 422

        _, target = _audit_rows("feedback.operator_labels_changed", actor_email=email)[-1]
        assert target == {"submission_id": str(submission), "label_count": 2}


def test_attachment_url_is_signed_after_the_row_check_and_audited(client: TestClient) -> None:
    with committed_workspace("httpatop") as operator, committed_workspace("httpatsrc") as other:
        submission, attachment = _seed(operator=operator, other=other)
        headers = _as(client, operator)
        email = operator_member(operator).email  # type: ignore[attr-defined]

        ok = client.get(
            f"/api/v1/platform/feedback/{submission}/attachments/{attachment}/url", headers=headers
        )
        assert ok.status_code == 200
        assert ok.json()["expires_in"] == 300
        assert ok.json()["url"].startswith("https://storage.example.test/")
        tenant_id, _ = _audit_rows("feedback.operator_attachment_url_issued", actor_email=email)[-1]
        assert tenant_id == other.tenant_id

        missing = client.get(
            f"/api/v1/platform/feedback/{submission}/attachments/{uuid4()}/url", headers=headers
        )
        assert missing.status_code == 404


def test_revoking_takes_effect_on_the_next_request(client: TestClient) -> None:
    with committed_workspace("httprvop") as operator, committed_workspace("httprvsrc") as other:
        _seed(operator=operator, other=other)
        headers = _as(client, operator)
        assert client.get("/api/v1/platform/feedback", headers=headers).status_code == 200

        with psycopg.connect(TEST_DATABASE_URL or "") as connection:
            connection.execute(
                "update platform_operator set revoked_at = now() where user_id = %s",
                (operator.user_id,),
            )
        # Same token, no expiry in between: the very next request is refused.
        assert client.get("/api/v1/platform/feedback", headers=headers).status_code == 404


def test_me_and_digest_preference_round_trip(client: TestClient) -> None:
    with committed_workspace("httpmeop") as operator, committed_workspace("httpmesrc") as other:
        _seed(operator=operator, other=other)
        headers = _as(client, operator)
        assert client.get("/api/v1/platform/feedback/me", headers=headers).json() == {
            "digest_enabled": False,
            "digest_locale": "en",
        }
        updated = client.put(
            "/api/v1/platform/feedback/digest-preference",
            json={"enabled": True, "locale": "ar"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json() == {"digest_enabled": True, "digest_locale": "ar"}
        email = operator_member(operator).email  # type: ignore[attr-defined]
        assert _audit_rows("feedback.digest_preference_changed", actor_email=email)
