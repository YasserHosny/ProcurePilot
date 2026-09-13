from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    Workspace,
    act_as,
    connection,
    make_workspace,
    reset_role,
)
from integration.quotation_helpers import PsycopgSupabaseClient
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import QualityIssueCreate
from procurepilot_api.modules.requests.service import RequestsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set; needs Postgres with R2.3 migrations",
)


@pytest.fixture
def conn() -> psycopg.Connection:
    yield from connection()


def _make_member(
    cur: psycopg.Cursor, tenant_id: UUID, label: str, role: str
) -> Workspace:
    user_id, membership_id = uuid4(), uuid4()
    cur.execute(
        "insert into auth.users (id,email) values (%s,%s)",
        (user_id, f"{label}@example.test"),
    )
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role,is_active_workspace) "
        "values (%s,%s,%s,%s,%s,true)",
        (membership_id, tenant_id, user_id, f"{label}@example.test", role),
    )
    return Workspace(tenant_id, user_id, membership_id, role, label)


def _make_branch(cur: psycopg.Cursor, workspace: Workspace, label: str) -> UUID:
    branch_id = uuid4()
    cur.execute(
        "insert into branch (id,tenant_id,name,region) values (%s,%s,%s,'GB')",
        (branch_id, workspace.tenant_id, label),
    )
    return branch_id


def _make_request(
    cur: psycopg.Cursor,
    workspace: Workspace,
    branch_id: UUID,
    requester: Workspace,
    *,
    status: str,
) -> UUID:
    request_id = uuid4()
    # purchase_request_delivered_at_pairing requires delivered_at to be set
    # exactly when status = 'delivered' (supabase/migrations/
    # 20260913000002_purchase_request_delivery_columns.sql).
    delivered_at = "now()" if status == "delivered" else "null"
    cur.execute(
        "insert into purchase_request "
        "(id,tenant_id,branch_id,requested_by_membership_id,required_by_date,status,"
        f"delivered_at) "
        f"values (%s,%s,%s,%s,current_date + interval '7 days',%s,{delivered_at})",
        (
            request_id,
            workspace.tenant_id,
            branch_id,
            requester.membership_id,
            status,
        ),
    )
    return request_id


def _current_member(workspace: Workspace, member_ws: Workspace) -> CurrentMember:
    return CurrentMember(
        membership_id=member_ws.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=member_ws.user_id,
        email=f"{member_ws.label}@example.test",
        role=MemberRole(member_ws.role),
    )


def _service(
    conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RequestsService, list[dict[str, object]]]:
    service = RequestsService()
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: PsycopgSupabaseClient(conn),
    )
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))
    return service, recorded


def test_quality_issue_with_zero_photos_persists_and_lists_with_empty_photos(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "quality-zero-photo")
        reporter = _make_member(
            cur, owner.tenant_id, "quality-zero-photo-reporter", "branch_manager"
        )
        branch_id = _make_branch(cur, owner, "Quality Zero Photo")
        request_id = _make_request(
            cur, owner, branch_id, reporter, status="delivered"
        )
    conn.commit()

    service, recorded = _service(conn, monkeypatch)
    created = service.create_quality_issue(
        bearer_token="token",
        member=_current_member(owner, reporter),
        request_id=request_id,
        payload=QualityIssueCreate(description="Damaged outer cartons"),
    )
    listed = service.list_quality_issues(
        bearer_token="token",
        request_id=request_id,
    )

    assert created.purchase_request_id == request_id
    assert created.reported_by_membership_id == reporter.membership_id
    assert created.description == "Damaged outer cartons"
    assert created.photos == []
    assert [row["action"] for row in recorded] == [
        "requests.quality_issue_reported"
    ]
    assert len(listed.items) == 1
    assert listed.items[0].id == created.id
    assert listed.items[0].photos == []

    with conn.cursor() as cur:
        cur.execute(
            "select purchase_request_id, reported_by_membership_id, description "
            "from delivery_quality_issue where id = %s",
            (created.id,),
        )
        assert cur.fetchone() == (
            request_id,
            reporter.membership_id,
            "Damaged outer cartons",
        )


def test_quality_issue_against_not_delivered_request_refuses_with_conflict(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        owner = make_workspace(cur, "quality-not-delivered")
        branch_id = _make_branch(cur, owner, "Quality Not Delivered")
        request_id = _make_request(
            cur, owner, branch_id, owner, status="ordered"
        )
    conn.commit()

    service, _recorded = _service(conn, monkeypatch)
    with pytest.raises(ConflictError) as exc:
        service.create_quality_issue(
            bearer_token="token",
            member=_current_member(owner, owner),
            request_id=request_id,
            payload=QualityIssueCreate(description="Cannot report yet"),
        )

    assert exc.value.status_code == 409
    assert exc.value.details == {"reason": "not_delivered"}


def test_quality_issue_photo_storage_object_from_another_workspace_is_invisible(
    conn: psycopg.Connection,
) -> None:
    with conn.cursor() as cur:
        alpha = make_workspace(cur, "quality-storage-alpha")
        beta = make_workspace(cur, "quality-storage-beta")
        alpha_path = (
            f"tenants/{alpha.tenant_id}/quality-issues/{uuid4()}/alpha.jpg"
        )
        beta_path = (
            f"tenants/{beta.tenant_id}/quality-issues/{uuid4()}/beta.jpg"
        )
        reset_role(cur)
        cur.execute(
            "insert into storage.objects (bucket_id,name,owner) "
            "values ('quality-issue-photos',%s,%s)",
            (alpha_path, alpha.user_id),
        )
        cur.execute(
            "insert into storage.objects (bucket_id,name,owner) "
            "values ('quality-issue-photos',%s,%s)",
            (beta_path, beta.user_id),
        )
        act_as(cur, alpha)
        cur.execute(
            "select name from storage.objects where bucket_id = 'quality-issue-photos' "
            "and name = %s",
            (beta_path,),
        )
        assert cur.fetchall() == []
        cur.execute(
            "select name from storage.objects where bucket_id = 'quality-issue-photos' "
            "and name = %s",
            (alpha_path,),
        )
        assert cur.fetchall() == [(alpha_path,)]
