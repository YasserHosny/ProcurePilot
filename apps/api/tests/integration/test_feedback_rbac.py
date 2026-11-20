"""Spec 025 T019, T031 and the RBAC part of T049.

Roles, ownership and the owner's read-only inbox. The HTTP-level 404 for non-owners on
GET /feedback is covered without a database in tests/contract/test_feedback_contract.py; the
service-level guard and row-level security are covered here.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from integration.feedback_db_helpers import (
    ALL_ROLES,
    committed_feedback_world,
    db_execute,
    db_rows,
    make_harness,
    requires_db,
    submit,
)
from integration.feedback_helpers import jpeg_bytes, png_bytes
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.schemas import Category, Status
from procurepilot_api.modules.feedback.validation import UploadedFile

pytestmark = requires_db


def _imgs() -> list[UploadedFile]:
    return [UploadedFile("a.jpg", jpeg_bytes(), None), UploadedFile("b.png", png_bytes(), None)]


# ------------------------------------------------------------------------ T019


@pytest.mark.parametrize("role", ALL_ROLES)
def test_each_role_submits_and_reads_its_own_and_never_sees_labels(
    monkeypatch: pytest.MonkeyPatch, role: MemberRole
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-submit") as world:
        member = world.member(role)
        result = submit(harness, member, text="visible to me", category=Category.question)
        db_execute(
            "update feedback_submission set labels = array['internal-only-label'] where id = %s",
            (result.submission.id,),
        )

        mine = harness.service.list_mine(member=member)
        one = harness.service.get(member=member, submission_id=result.submission.id)

        assert [item.id for item in mine.items] == [result.submission.id]
        assert one.id == result.submission.id
        for payload in (result.submission, mine, one):
            dumped = json.dumps(payload.model_dump(mode="json"))
            assert "labels" not in dumped
            assert "internal-only-label" not in dumped


# ------------------------------------------------------------------------ T031


def test_attachment_url_for_submitter_owner_but_not_colleague_or_other_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-url") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(harness, buyer, images=_imgs())
        (first, _second) = result.submission.attachments
        sid, aid = result.submission.id, first.id

        own = harness.service.attachment_url(member=buyer, submission_id=sid, attachment_id=aid)
        assert own.expires_in == 300
        (path_row,) = db_rows("select storage_path from feedback_attachment where id = %s", (aid,))
        assert own.url == f"http://storage.test/{path_row['storage_path']}?token=t"

        owner = harness.service.attachment_url(
            member=world.member(MemberRole.owner), submission_id=sid, attachment_id=aid
        )
        assert owner.url == own.url

        for stranger in (
            world.member(MemberRole.viewer),
            world.member(MemberRole.approver),
            world.other_owner,
        ):
            with pytest.raises(NotFoundError):
                harness.service.attachment_url(
                    member=stranger, submission_id=sid, attachment_id=aid
                )


def test_attachment_url_with_a_mismatched_submission_or_unknown_id_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-url-404") as world:
        buyer = world.member(MemberRole.buyer)
        one = submit(harness, buyer, images=_imgs())
        two = submit(harness, buyer, images=_imgs())
        with pytest.raises(NotFoundError):  # attachment of `one` asked for under `two`
            harness.service.attachment_url(
                member=buyer,
                submission_id=two.submission.id,
                attachment_id=one.submission.attachments[0].id,
            )
        with pytest.raises(NotFoundError):
            harness.service.attachment_url(
                member=buyer, submission_id=one.submission.id, attachment_id=uuid4()
            )


def test_a_stored_object_missing_from_the_bucket_is_a_server_error_not_a_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.errors import ServiceUnavailableError

    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-url-gone") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(harness, buyer, images=_imgs())
        harness.storage.objects.clear()
        with pytest.raises(ServiceUnavailableError):
            harness.service.attachment_url(
                member=buyer,
                submission_id=result.submission.id,
                attachment_id=result.submission.attachments[0].id,
            )


# ------------------------------------------------------------------- T049 (rbac)


def test_a_member_sees_only_their_own_and_the_owner_sees_the_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-visibility") as world:
        ids = {
            role: submit(harness, world.member(role), text=f"from {role.value}").submission.id
            for role in ALL_ROLES
        }

        for role in ALL_ROLES:
            mine = harness.service.list_mine(member=world.member(role))
            assert [i.id for i in mine.items] == [ids[role]]
            assert all(i.submitter_name is None for i in mine.items)  # names are owner-inbox only
            for other_role in ALL_ROLES:
                if other_role == role:
                    continue
                if role == MemberRole.owner:
                    # The owner may open any item in the workspace.
                    harness.service.get(member=world.member(role), submission_id=ids[other_role])
                else:
                    with pytest.raises(NotFoundError):
                        harness.service.get(
                            member=world.member(role), submission_id=ids[other_role]
                        )

        inbox = harness.service.list_workspace(member=world.member(MemberRole.owner))
        assert {i.id for i in inbox.items} == set(ids.values())
        assert all(i.submitter_name for i in inbox.items)
        # can_withdraw is only ever true for the owner's own item.
        assert {i.id for i in inbox.items if i.can_withdraw} == {ids[MemberRole.owner]}


@pytest.mark.parametrize("role", [r for r in ALL_ROLES if r != MemberRole.owner])
def test_the_workspace_inbox_is_404_for_non_owners(
    monkeypatch: pytest.MonkeyPatch, role: MemberRole
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-inbox") as world:
        submit(harness, world.member(MemberRole.buyer))
        with pytest.raises(NotFoundError):
            harness.service.list_workspace(member=world.member(role))


def test_the_workspace_inbox_filters_and_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-page") as world:
        buyer, owner = world.member(MemberRole.buyer), world.member(MemberRole.owner)
        created = [
            submit(harness, buyer, text=f"n{i}", category=Category.bug if i % 2 else Category.idea)
            for i in range(5)
        ]
        db_execute(
            "update feedback_submission set status = 'reviewed' where id = %s",
            (created[0].submission.id,),
        )
        db_execute(
            "update feedback_submission set created_at = now() - make_interval(mins => %s) "
            "where id = %s",
            (10 - 1, created[0].submission.id),
            bypass_triggers=True,
        )

        reviewed = harness.service.list_workspace(member=owner, status=Status.reviewed)
        assert [i.id for i in reviewed.items] == [created[0].submission.id]
        bugs = harness.service.list_workspace(member=owner, category=Category.bug)
        assert {i.category for i in bugs.items} == {Category.bug}

        seen: list = []
        cursor = None
        while True:
            page = harness.service.list_workspace(member=owner, cursor=cursor, limit=2)
            assert len(page.items) <= 2
            seen.extend(i.id for i in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert sorted(seen) == sorted(c.submission.id for c in created)
        assert len(seen) == len(set(seen))
        # Newest first.
        first_page = harness.service.list_workspace(member=owner, limit=100)
        stamps = [i.created_at for i in first_page.items]
        assert stamps == sorted(stamps, reverse=True)


def test_limit_is_clamped_to_100_in_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-clamp") as world:
        submit(harness, world.member(MemberRole.buyer))
        page = harness.service.list_mine(member=world.member(MemberRole.buyer), limit=10_000)
        assert len(page.items) == 1


def test_no_role_can_change_status_or_labels_through_row_level_security(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Members hold a column grant but no update policy, so an UPDATE changes nothing."""
    import psycopg

    from integration.catalogue_helpers import TEST_DATABASE_URL

    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-rbac-noupdate") as world:
        result = submit(harness, world.member(MemberRole.buyer))
        for role in ALL_ROLES:
            member = world.member(role)
            with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None) as conn:
                with conn.cursor() as cur:
                    cur.execute("set local role feedback_app")
                    cur.execute(
                        "select set_config('request.jwt.claims', %s, true)",
                        (
                            json.dumps(
                                {
                                    "sub": str(member.user_id),
                                    "tenant_id": str(member.tenant_id),
                                    "role": "authenticated",
                                    "member_role": role.value,
                                }
                            ),
                        ),
                    )
                    cur.execute(
                        "update feedback_submission set status = 'resolved', "
                        "labels = array['x'] where id = %s",
                        (result.submission.id,),
                    )
                    assert cur.rowcount == 0, f"{role.value} must not be able to update"
        (row,) = db_rows(
            "select status, labels from feedback_submission where id = %s", (result.submission.id,)
        )
        assert row == {"status": "new", "labels": []}
