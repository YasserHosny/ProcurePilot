"""Spec 025 T049: what each caller can see through the member and owner API.

Named `test_feedback_visibility.py` rather than `test_feedback_isolation.py`: that file name is
T005's (schema-level isolation, written by the migration work), so the two do not collide.
These tests go through the service, which is what the routes call.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from integration.feedback_db_helpers import (
    committed_feedback_world,
    db_execute,
    db_rows,
    make_harness,
    requires_db,
    submit,
)
from integration.feedback_helpers import jpeg_bytes
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.validation import UploadedFile

pytestmark = requires_db


def test_another_workspaces_items_are_invisible_to_list_get_withdraw_and_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-iso") as world:
        mine = submit(
            harness,
            world.member(MemberRole.buyer),
            images=[UploadedFile("a.jpg", jpeg_bytes(), None)],
        )
        theirs = submit(
            harness,
            world.other_owner,
            text="other workspace",
            images=[UploadedFile("b.jpg", jpeg_bytes(), None)],
        )
        sid, aid = mine.submission.id, mine.submission.attachments[0].id

        # The other workspace's owner reads their whole inbox: only their own item.
        inbox = harness.service.list_workspace(member=world.other_owner)
        assert [i.id for i in inbox.items] == [theirs.submission.id]
        assert harness.service.list_mine(member=world.other_owner).items[0].id == (
            theirs.submission.id
        )
        # And ours never sees theirs.
        ours = harness.service.list_workspace(member=world.member(MemberRole.owner))
        assert [i.id for i in ours.items] == [sid]

        # Cross-tenant ids are "not found", never "forbidden".
        with pytest.raises(NotFoundError):
            harness.service.get(member=world.other_owner, submission_id=sid)
        with pytest.raises(NotFoundError):
            harness.service.withdraw(member=world.other_owner, bearer_token="t", submission_id=sid)
        with pytest.raises(NotFoundError):
            harness.service.attachment_url(
                member=world.other_owner, submission_id=sid, attachment_id=aid
            )
        with pytest.raises(NotFoundError):
            harness.service.get(
                member=world.member(MemberRole.owner), submission_id=theirs.submission.id
            )
        assert len(db_rows("select 1 from feedback_submission where id = %s", (sid,))) == 1


def test_a_claim_naming_another_workspace_still_reads_only_its_own_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tenant comes from the claim; asking for another tenant's id changes nothing."""
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-iso-claim") as world:
        theirs = submit(harness, world.other_owner, text="secret of the other workspace")
        spoof = world.member(MemberRole.owner).model_copy(update={"user_id": uuid4()})
        assert harness.service.list_workspace(member=spoof).items == []
        with pytest.raises(NotFoundError):
            harness.service.get(member=spoof, submission_id=theirs.submission.id)


def test_no_tenant_facing_payload_contains_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-labels") as world:
        buyer, owner = world.member(MemberRole.buyer), world.member(MemberRole.owner)
        result = submit(harness, buyer, images=[UploadedFile("a.jpg", jpeg_bytes(), None)])
        db_execute(
            "update feedback_submission set labels = array['triage-secret', 'p1'] where id = %s",
            (result.submission.id,),
        )
        payloads = [
            harness.service.list_mine(member=buyer),
            harness.service.list_workspace(member=owner),
            harness.service.get(member=buyer, submission_id=result.submission.id),
            harness.service.get(member=owner, submission_id=result.submission.id),
        ]
        for payload in payloads:
            text = json.dumps(payload.model_dump(mode="json"))
            assert "labels" not in text
            assert "triage-secret" not in text


def test_after_the_submitters_membership_is_removed_the_owner_still_sees_the_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-former") as world:
        viewer, owner = world.member(MemberRole.viewer), world.member(MemberRole.owner)
        result = submit(harness, viewer, text="feedback from someone who left")

        db_execute("delete from membership where id = %s", (viewer.membership_id,))

        (row,) = db_rows(
            "select submitter_membership_id, submitter_name, submitter_email "
            "from feedback_submission where id = %s",
            (result.submission.id,),
        )
        assert row["submitter_membership_id"] is None  # on delete set null
        assert row["submitter_email"] == viewer.email  # the snapshot survives
        inbox = harness.service.list_workspace(member=owner)
        assert [i.id for i in inbox.items] == [result.submission.id]
        assert inbox.items[0].submitter_name == viewer.email
        assert inbox.items[0].can_withdraw is False
        # A former member's token no longer passes `current_member` (live membership check,
        # 401 `active_membership_not_found`), so they never reach this service. Row-level
        # security alone would still match their user id, which is why that check matters.


def test_listing_opens_one_connection_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Attachments are fetched in the list's own connection, not one connection per item."""
    from procurepilot_api import db

    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-conn") as world:
        buyer = world.member(MemberRole.buyer)
        for i in range(3):
            submit(
                harness, buyer, text=f"n{i}", images=[UploadedFile("a.jpg", jpeg_bytes(i), None)]
            )

        opened = 0
        real_connect = db.connect

        def counting_connect(*args: object, **kwargs: object) -> object:
            nonlocal opened
            opened += 1
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(db, "connect", counting_connect)
        page = harness.service.list_mine(member=buyer)
        assert len(page.items) == 3 and all(len(i.attachments) == 1 for i in page.items)
        assert opened == 1
