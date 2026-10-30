"""Members have a name (PPS-125): set from the invitation, editable in Team Management.

The Approval Queue showed an email because membership had no name. These cover the members API
writing and reading membership.display_name; the requests side is in
test_backend_web_lane_additions.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, make_workspace
from integration.quotation_helpers import PsycopgSupabaseClient
from integration.smart_compare_helpers import member_from_workspace, settings_for_test_db
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.members import invitations as invitations_module
from procurepilot_api.modules.members import service as members_module
from procurepilot_api.modules.members.models import (
    MemberInvitationCreate,
    Membership,
    MemberUpdate,
    MeUpdate,
)

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(TEST_DATABASE_URL or "", prepare_threshold=None) as connection:
        yield connection
        connection.rollback()


def _add_buyer(cur: psycopg.Cursor, workspace: Workspace) -> UUID:
    user_id, membership_id = uuid4(), uuid4()
    email = f"buyer-{user_id.hex[:10]}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (user_id, email))
    cur.execute(
        "insert into membership (id,tenant_id,user_id,email,role) values (%s,%s,%s,%s,'buyer')",
        (membership_id, workspace.tenant_id, user_id, email),
    )
    return membership_id


def test_an_owner_names_a_member_and_the_team_list_shows_it(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    cur = conn.cursor()
    workspace = make_workspace(cur, "names-owner")
    buyer_id = _add_buyer(cur, workspace)
    client = PsycopgSupabaseClient(conn, claims=workspace.claims())
    monkeypatch.setattr(members_module, "authenticated_client", lambda *_: client)
    service = members_module.MemberService(settings_for_test_db(monkeypatch))

    updated = service.update_member(
        bearer_token="test-token",
        actor=member_from_workspace(workspace),
        member_id=buyer_id,
        patch=MemberUpdate(display_name="  المشتري  "),
    )

    assert updated.display_name == "المشتري"
    assert updated.role == "buyer"
    listed = {m.id: m for m in service.list_members(bearer_token="test-token").items}
    assert listed[buyer_id].display_name == "المشتري"
    assert listed[workspace.membership_id].display_name is None


def test_a_member_sets_their_own_name(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    cur = conn.cursor()
    workspace = make_workspace(cur, "names-self")
    client = PsycopgSupabaseClient(conn, claims=workspace.claims())
    monkeypatch.setattr(members_module, "authenticated_client", lambda *_: client)
    service = members_module.MemberService(settings_for_test_db(monkeypatch))

    me = service.update_me(
        bearer_token="test-token",
        member=member_from_workspace(workspace),
        patch=MeUpdate(display_name="المالك"),
    )

    assert me.display_name == "المالك"


@pytest.mark.parametrize("payload", [{}, {"display_name": "   "}, {"display_name": "x" * 101}])
def test_a_member_update_needs_a_role_or_a_real_name(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MemberUpdate.model_validate(payload)


def test_accepting_an_invitation_copies_its_name_onto_the_membership(
    conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    cur = conn.cursor()
    workspace = make_workspace(cur, "names-invite")
    invitee_user, email = uuid4(), f"invitee-{uuid4().hex[:10]}@example.test"
    cur.execute("insert into auth.users (id,email) values (%s,%s)", (invitee_user, email))
    token_hash = f"hash-{uuid4().hex}"
    cur.execute(
        "insert into member_invitation "
        "(tenant_id,email,role,token_hash,invited_by,expires_at,status,display_name) "
        "values (%s,%s,'buyer',%s,%s,%s,'pending','المشتري') returning id",
        (
            workspace.tenant_id,
            email,
            token_hash,
            workspace.membership_id,
            datetime.now(UTC) + timedelta(days=7),
        ),
    )
    invitation_id = cur.fetchone()[0]
    conn.commit()
    try:
        settings = settings_for_test_db(monkeypatch)
        repository = invitations_module.SupabaseMemberInvitationRepository(settings)

        def find_membership(*, tenant_id: UUID, user_id: UUID) -> Membership:
            row = cur.execute(
                "select * from membership where tenant_id = %s and user_id = %s",
                (tenant_id, user_id),
            ).fetchone()
            columns = [c.name for c in cur.description]
            return Membership.model_validate(dict(zip(columns, row, strict=True)))

        monkeypatch.setattr(repository, "find_membership", find_membership)
        invitation = invitations_module.MemberInvitationRecord(
            id=invitation_id,
            tenant_id=workspace.tenant_id,
            email=email,
            role=MemberRole.buyer,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            token_hash=token_hash,
            invited_by=workspace.membership_id,
            display_name="المشتري",
        )

        membership = repository.accept(
            bearer_token="",
            invitation=invitation,
            user_id=invitee_user,
            email=email,
            token_hash=token_hash,
        )

        assert membership.display_name == "المشتري"
        assert MemberInvitationCreate(email=email, role=MemberRole.buyer).display_name is None
    finally:
        conn.rollback()
        cur.execute("set session_replication_role = replica")
        cur.execute("delete from tenant where id = %s", (workspace.tenant_id,))
        cur.execute(
            "delete from auth.users where id = any(%s)", ([invitee_user, workspace.user_id],)
        )
        cur.execute("set session_replication_role = origin")
        conn.commit()
