"""Spec 025 T017, T018, T030, T042 and T050: submit, cooldown, files, audio, withdraw.

Needs TEST_DATABASE_URL pointing at a Postgres with the spec 025 migrations applied. The
bucket and the audit writer are in-memory fakes; the database is real, so row-level security,
the unique indexes and the forward-only status trigger are all exercised.
"""

from __future__ import annotations

import threading
from uuid import uuid4

import psycopg
import pytest

from integration.feedback_db_helpers import (
    ALL_ROLES,
    Harness,
    committed_feedback_world,
    db_execute,
    db_rows,
    make_harness,
    requires_db,
    submit,
)
from integration.feedback_helpers import (
    MIB,
    TEXT_BYTES,
    audio_fixture,
    jpeg_bytes,
    png_bytes,
    webp_bytes,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    FeedbackCooldownError,
    FeedbackWithdrawRefusedError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.schemas import Category
from procurepilot_api.modules.feedback.validation import UploadedFile

pytestmark = requires_db


def _img(name: str, content: bytes | None = None) -> UploadedFile:
    return UploadedFile(name, content if content is not None else jpeg_bytes(), None)


# ------------------------------------------------------------------ T017: submit


@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_can_submit_and_the_server_sets_the_context(
    monkeypatch: pytest.MonkeyPatch, role: MemberRole
) -> None:
    harness = make_harness(monkeypatch, app_version="2026.11.18-abc")
    with committed_feedback_world("fb-roles") as world:
        member = world.member(role)
        result = submit(harness, member, text="  The totals look wrong  ", category=Category.bug)

        assert result.created is True
        assert result.submission.text == "The totals look wrong"
        assert result.submission.status.value == "new"
        assert result.submission.member_role == role
        assert result.submission.can_withdraw is True
        (row,) = db_rows("select * from feedback_submission where id = %s", (result.submission.id,))
        assert row["tenant_id"] == world.workspace.tenant_id
        assert row["submitter_user_id"] == member.user_id
        assert row["submitter_membership_id"] == member.membership_id
        assert row["member_role"] == role.value
        assert row["submitter_email"] == member.email
        assert row["category"] == "bug"
        assert row["status"] == "new"
        assert row["labels"] == []
        assert row["app_version"] == "2026.11.18-abc"
        assert row["is_demo"] is False
        assert row["created_at"] is not None


def test_name_is_snapshotted_from_display_name_with_email_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-name") as world:
        named, unnamed = world.member(MemberRole.buyer), world.member(MemberRole.viewer)
        db_execute(
            "update membership set display_name = %s where id = %s",
            ("Salma Fathy", named.membership_id),
        )
        first = submit(harness, named)
        second = submit(harness, unnamed)

        names = {
            r["id"]: r["submitter_name"]
            for r in db_rows(
                "select id, submitter_name from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
        }
        assert names[first.submission.id] == "Salma Fathy"
        assert names[second.submission.id] == unnamed.email

        # Renaming the member later does not rewrite history.
        db_execute(
            "update membership set display_name = %s where id = %s",
            ("Someone Else", named.membership_id),
        )
        (row,) = db_rows(
            "select submitter_name from feedback_submission where id = %s", (first.submission.id,)
        )
        assert row["submitter_name"] == "Salma Fathy"


def test_demo_flag_and_app_version_are_copied_at_submit_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch, app_version="v-one")
    with committed_feedback_world("fb-demo") as world:
        db_execute("update tenant set is_demo = true where id = %s", (world.workspace.tenant_id,))
        result = submit(harness, world.member(MemberRole.buyer))
        db_execute("update tenant set is_demo = false where id = %s", (world.workspace.tenant_id,))
        (row,) = db_rows(
            "select is_demo, app_version from feedback_submission where id = %s",
            (result.submission.id,),
        )
        assert row == {"is_demo": True, "app_version": "v-one"}


@pytest.mark.parametrize("text", ["", "   ", "\n\t  \n"])
def test_empty_or_blank_text_is_422(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-blank") as world:
        with pytest.raises(UnprocessableEntityError):
            submit(harness, world.member(MemberRole.buyer), text=text)
        assert (
            db_rows(
                "select 1 from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
            == []
        )


def test_text_limit_is_2000_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-limit") as world:
        buyer = world.member(MemberRole.buyer)
        assert submit(harness, buyer, text="ش" * 2000).created
        with pytest.raises(UnprocessableEntityError):
            submit(harness, buyer, text="x" * 2001)


def test_page_path_and_language_come_from_validated_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-headers") as world:
        buyer = world.member(MemberRole.buyer)
        good = submit(
            harness,
            buyer,
            referer="http://localhost:4200/requests/42?tab=lines#x",
            accept_language="ar-EG,ar;q=0.9,en;q=0.5",
        )
        foreign = submit(
            harness, buyer, referer="https://evil.example/requests/42", accept_language="fr"
        )
        rows = {
            r["id"]: r
            for r in db_rows(
                "select id, page_path, locale from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
        }
        assert rows[good.submission.id]["page_path"] == "/requests/42?tab=lines"
        assert rows[good.submission.id]["locale"] == "ar"
        assert rows[foreign.submission.id]["page_path"] == ""
        # "fr" is unsupported: the workspace default applies.
        (tenant,) = db_rows(
            "select default_locale from tenant where id = %s", (world.workspace.tenant_id,)
        )
        assert rows[foreign.submission.id]["locale"] == tenant["default_locale"]


def test_workspace_default_language_applies_without_a_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-locale") as world:
        db_execute(
            "update tenant set default_locale = 'ar' where id = %s", (world.workspace.tenant_id,)
        )
        result = submit(harness, world.member(MemberRole.buyer))
        assert result.submission.locale == "ar"


def test_submitting_writes_a_content_free_audit_event(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-audit") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(
            harness,
            buyer,
            text="private words",
            category=Category.idea,
            images=[_img("a.jpg")],
            audio=UploadedFile("n.wav", audio_fixture("tone.wav"), None),
        )
        ((event, token),) = harness.audit.events
        assert event.action == "feedback.submitted"
        assert event.outcome == "success"
        assert event.tenant_id == world.workspace.tenant_id
        assert event.actor_membership_id == buyer.membership_id
        assert event.target == {
            "submission_id": str(result.submission.id),
            "category": "idea",
            "image_count": 1,
            "has_audio": True,
        }
        assert "private words" not in repr(event)
        # Written on the submission's own transaction (debate-review F5), not with a bearer token.
        assert token is None


def test_category_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-nocat") as world:
        result = submit(harness, world.member(MemberRole.buyer))
        assert result.submission.category is None
        (row,) = db_rows(
            "select category from feedback_submission where id = %s", (result.submission.id,)
        )
        assert row["category"] is None


# ----------------------------------------------------- T018: cooldown, idempotency


def test_second_submit_inside_the_cooldown_is_refused_with_time_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch, cooldown_seconds=30)
    with committed_feedback_world("fb-cool") as world:
        buyer, viewer = world.member(MemberRole.buyer), world.member(MemberRole.viewer)
        submit(harness, buyer)
        with pytest.raises(FeedbackCooldownError) as caught:
            submit(harness, buyer, text="another one")
        assert 1 <= caught.value.details["retry_after_seconds"] <= 30  # type: ignore[index]
        assert caught.value.status_code == 429
        assert caught.value.code == "feedback.cooldown"
        assert (
            len(
                db_rows(
                    "select 1 from feedback_submission where tenant_id = %s",
                    (world.workspace.tenant_id,),
                )
            )
            == 1
        )

        # The cooldown is per member: a colleague is unaffected.
        assert submit(harness, viewer).created


def test_cooldown_ends_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch, cooldown_seconds=30)
    with committed_feedback_world("fb-cool-end") as world:
        buyer = world.member(MemberRole.buyer)
        first = submit(harness, buyer)
        db_execute(
            "update feedback_submission set created_at = now() - interval '31 seconds' "
            "where id = %s",
            (first.submission.id,),
            bypass_triggers=True,
        )
        assert submit(harness, buyer, text="after the wait").created


def test_replay_with_the_same_key_returns_the_original_and_skips_the_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch, cooldown_seconds=30)
    with committed_feedback_world("fb-replay") as world:
        buyer = world.member(MemberRole.buyer)
        key = uuid4()
        first = submit(harness, buyer, key=key, text="original")
        again = submit(harness, buyer, key=key, text="original")  # still inside the cooldown

        assert first.created is True and again.created is False
        assert again.submission.id == first.submission.id
        assert again.submission.text == "original"
        assert (
            len(
                db_rows(
                    "select 1 from feedback_submission where tenant_id = %s",
                    (world.workspace.tenant_id,),
                )
            )
            == 1
        )
        assert harness.audit.actions() == ["feedback.submitted"]  # the replay adds no event


def test_a_key_used_by_a_colleague_is_a_conflict_not_a_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-key-clash") as world:
        key = uuid4()
        submit(harness, world.member(MemberRole.buyer), key=key)
        # The owner can read every submission, but a replay never returns someone else's.
        with pytest.raises(ConflictError):
            submit(harness, world.member(MemberRole.owner), key=key)
        assert (
            len(
                db_rows(
                    "select 1 from feedback_submission where tenant_id = %s",
                    (world.workspace.tenant_id,),
                )
            )
            == 1
        )


def test_parallel_requests_with_one_key_store_exactly_one_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch, cooldown_seconds=30)
    with committed_feedback_world("fb-parallel") as world:
        buyer = world.member(MemberRole.buyer)
        key = uuid4()
        barrier = threading.Barrier(4)
        results: list[object] = []

        def worker() -> None:
            barrier.wait()
            try:
                results.append(submit(harness, buyer, key=key, text="double click"))
            except Exception as exc:  # noqa: BLE001 - collected and asserted below
                results.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not [r for r in results if isinstance(r, Exception)], results
        assert sorted(r.created for r in results) == [False, False, False, True]  # type: ignore[union-attr]
        assert len({r.submission.id for r in results}) == 1  # type: ignore[union-attr]
        assert (
            len(
                db_rows(
                    "select 1 from feedback_submission where tenant_id = %s",
                    (world.workspace.tenant_id,),
                )
            )
            == 1
        )


# ------------------------------------------------------------- T030: screenshots


def test_five_images_are_stored_with_rows_and_tenant_prefixed_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-img5") as world:
        buyer = world.member(MemberRole.buyer)
        images = [
            _img("a.jpg", jpeg_bytes()),
            _img("b.png", png_bytes()),
            _img("c.webp", webp_bytes()),
            _img("d.jpg", jpeg_bytes(extra=5)),
            _img("e.png", png_bytes(extra=5)),
        ]
        result = submit(harness, buyer, images=images)

        sid = result.submission.id
        rows = db_rows(
            "select * from feedback_attachment where submission_id = %s order by display_order",
            (sid,),
        )
        assert [r["display_order"] for r in rows] == [0, 1, 2, 3, 4]
        assert [r["kind"] for r in rows] == ["image"] * 5
        assert [r["content_type"] for r in rows] == [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/jpeg",
            "image/png",
        ]
        assert [r["size_bytes"] for r in rows] == [len(i.content) for i in images]
        prefix = f"tenants/{world.workspace.tenant_id}/feedback/{sid}/"
        assert all(r["storage_path"].startswith(prefix) for r in rows)
        assert {r["storage_path"] for r in rows} == set(harness.storage.objects)
        assert all(r["tenant_id"] == world.workspace.tenant_id for r in rows)
        assert [a.display_order for a in result.submission.attachments] == [0, 1, 2, 3, 4]
        assert harness.storage.tokens == ["member-jwt"] * 5  # uploaded as the member


def test_a_sixth_image_wrong_type_and_oversize_are_refused_and_store_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-img-bad") as world:
        buyer = world.member(MemberRole.buyer)
        with pytest.raises(UnprocessableEntityError):
            submit(harness, buyer, images=[_img(f"{i}.jpg") for i in range(6)])
        with pytest.raises(UnsupportedMediaTypeError):
            submit(harness, buyer, images=[_img("fake.png", TEXT_BYTES)])
        with pytest.raises(PayloadTooLargeError):
            submit(harness, buyer, images=[_img("big.jpg", jpeg_bytes(extra=5 * MIB))])

        assert harness.storage.objects == {}
        assert harness.storage.upload_calls == 0
        assert (
            db_rows(
                "select 1 from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
            == []
        )


def test_a_failure_on_the_third_upload_leaves_no_rows_and_no_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    harness.storage.fail_on_upload = 3
    with committed_feedback_world("fb-atomic") as world:
        buyer = world.member(MemberRole.buyer)
        with pytest.raises(ServiceUnavailableError):
            submit(harness, buyer, images=[_img(f"{i}.jpg", jpeg_bytes(extra=i)) for i in range(5)])

        assert harness.storage.objects == {}, "the two objects uploaded before the failure"
        assert sum(len(c) for c in harness.storage.delete_calls) == 2
        assert (
            db_rows(
                "select 1 from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
            == []
        )
        assert (
            db_rows(
                "select 1 from feedback_attachment where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
            == []
        )
        assert harness.audit.events == []

        # The same key can be retried once the dependency recovers.
        harness.storage.fail_on_upload = None
        assert submit(harness, buyer, images=[_img("a.jpg")]).created


def test_a_database_failure_after_uploading_removes_the_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-db-fail") as world:

        def boom(*_args: object, **_kwargs: object) -> None:
            raise psycopg.errors.CheckViolation("injected")

        monkeypatch.setattr(type(harness.service), "_insert_attachments", boom)
        with pytest.raises(ServiceUnavailableError):
            submit(harness, world.member(MemberRole.buyer), images=[_img("a.jpg"), _img("b.jpg")])
        assert harness.storage.objects == {}
        assert (
            db_rows(
                "select 1 from feedback_submission where tenant_id = %s",
                (world.workspace.tenant_id,),
            )
            == []
        )


def test_idempotent_replay_with_files_creates_no_second_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch, cooldown_seconds=30)
    with committed_feedback_world("fb-replay-files") as world:
        buyer = world.member(MemberRole.buyer)
        key = uuid4()
        images = [_img("a.jpg"), _img("b.png", png_bytes())]
        first = submit(harness, buyer, key=key, images=images)
        again = submit(harness, buyer, key=key, images=images)

        assert again.created is False
        assert [a.id for a in again.submission.attachments] == [
            a.id for a in first.submission.attachments
        ]
        assert harness.storage.upload_calls == 2
        assert len(harness.storage.objects) == 2
        assert (
            len(
                db_rows(
                    "select 1 from feedback_attachment where tenant_id = %s",
                    (world.workspace.tenant_id,),
                )
            )
            == 2
        )


# ------------------------------------------------------------------- T042: audio

_AUDIO_FIXTURES = [
    ("recorded-chrome.webm", "audio/webm"),
    ("recorded-chrome.mp4", "audio/mp4"),
    ("recorded-safari-style.mp4", "audio/mp4"),
    ("voice.m4a", "audio/mp4"),
    ("silence.mp3", "audio/mpeg"),
    ("tone.wav", "audio/wav"),
]


@pytest.mark.parametrize(("name", "stored_type"), _AUDIO_FIXTURES)
def test_audio_is_stored_as_kind_audio(
    monkeypatch: pytest.MonkeyPatch, name: str, stored_type: str
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-audio") as world:
        content = audio_fixture(name)
        result = submit(
            harness, world.member(MemberRole.buyer), audio=UploadedFile(name, content, None)
        )
        (row,) = db_rows(
            "select kind, content_type, size_bytes, display_order, storage_path "
            "from feedback_attachment where submission_id = %s",
            (result.submission.id,),
        )
        assert row["kind"] == "audio"
        assert row["content_type"] == stored_type
        assert row["size_bytes"] == len(content)
        assert row["display_order"] == 0
        assert harness.storage.objects[row["storage_path"]] == content


def test_renamed_fake_audio_is_415_and_oversize_audio_is_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-audio-bad") as world:
        buyer = world.member(MemberRole.buyer)
        with pytest.raises(UnsupportedMediaTypeError):
            submit(
                harness,
                buyer,
                audio=UploadedFile("voice.mp3", audio_fixture("renamed-fake.mp3"), None),
            )
        big = audio_fixture("tone.wav") + b"\x00" * (10 * MIB)
        with pytest.raises(PayloadTooLargeError):
            submit(harness, buyer, audio=UploadedFile("voice.wav", big, None))
        assert harness.storage.objects == {}


def test_images_and_one_audio_together(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-both") as world:
        result = submit(
            harness,
            world.member(MemberRole.buyer),
            images=[_img("a.jpg"), _img("b.png", png_bytes())],
            audio=UploadedFile("n.webm", audio_fixture("recorded-chrome.webm"), None),
        )
        assert [(a.kind.value, a.display_order) for a in result.submission.attachments] == [
            ("image", 0),
            ("image", 1),
            ("audio", 0),
        ]


# ------------------------------------------------------------------ T050: withdraw


def test_withdrawing_a_new_item_removes_row_attachments_and_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-withdraw") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(
            harness,
            buyer,
            text="regrettable text",
            images=[_img("a.jpg"), _img("b.png", png_bytes())],
            audio=UploadedFile("n.wav", audio_fixture("tone.wav"), None),
        )
        assert len(harness.storage.objects) == 3

        harness.service.withdraw(
            member=buyer, bearer_token="member-jwt", submission_id=result.submission.id
        )

        assert (
            db_rows("select 1 from feedback_submission where id = %s", (result.submission.id,))
            == []
        )
        assert (
            db_rows(
                "select 1 from feedback_attachment where submission_id = %s",
                (result.submission.id,),
            )
            == []
        )
        assert harness.storage.objects == {}
        assert harness.audit.actions() == ["feedback.submitted", "feedback.withdrawn"]
        event, _token = harness.audit.events[-1]
        assert event.target == {"submission_id": str(result.submission.id)}
        assert "regrettable" not in repr(event)


def test_withdrawal_whose_object_delete_fails_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-withdraw-leak") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(harness, buyer, images=[_img("a.jpg")])
        harness.storage.delete = lambda paths: list(paths)  # type: ignore[method-assign]

        harness.service.withdraw(
            member=buyer, bearer_token="member-jwt", submission_id=result.submission.id
        )
        assert (
            db_rows("select 1 from feedback_submission where id = %s", (result.submission.id,))
            == []
        )
        assert len(harness.storage.objects) == 1  # left for the orphan sweep


@pytest.mark.parametrize("status", ["reviewed", "resolved"])
def test_withdrawing_after_the_status_moved_is_409(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-withdraw-late") as world:
        buyer = world.member(MemberRole.buyer)
        result = submit(harness, buyer, images=[_img("a.jpg")])
        db_execute(
            "update feedback_submission set status = %s::feedback_status where id = %s",
            (status, result.submission.id),
        )
        with pytest.raises(FeedbackWithdrawRefusedError) as caught:
            harness.service.withdraw(
                member=buyer, bearer_token="member-jwt", submission_id=result.submission.id
            )
        assert caught.value.status_code == 409
        assert caught.value.code == "feedback.withdraw_refused"
        assert (
            len(db_rows("select 1 from feedback_submission where id = %s", (result.submission.id,)))
            == 1
        )
        assert len(harness.storage.objects) == 1
        assert "feedback.withdrawn" not in harness.audit.actions()


def test_only_the_submitter_can_withdraw_and_everyone_else_gets_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-withdraw-404") as world:
        result = submit(harness, world.member(MemberRole.buyer))
        for stranger in (
            world.member(MemberRole.owner),  # the owner sees it but cannot withdraw it
            world.member(MemberRole.viewer),
            world.other_owner,
        ):
            with pytest.raises(NotFoundError):
                harness.service.withdraw(
                    member=stranger, bearer_token="t", submission_id=result.submission.id
                )
        with pytest.raises(NotFoundError):
            harness.service.withdraw(
                member=world.member(MemberRole.buyer), bearer_token="t", submission_id=uuid4()
            )
        assert (
            len(db_rows("select 1 from feedback_submission where id = %s", (result.submission.id,)))
            == 1
        )


def _race_withdraw_against_review(harness: Harness, buyer: CurrentMember) -> str:
    """Withdraw and an operator-style status change released together; returns who won."""
    sid = submit(harness, buyer).submission.id
    barrier = threading.Barrier(2)
    withdraw_outcome: list[str] = []

    def do_withdraw() -> None:
        barrier.wait()
        try:
            harness.service.withdraw(member=buyer, bearer_token="t", submission_id=sid)
            withdraw_outcome.append("withdrawn")
        except FeedbackWithdrawRefusedError:
            withdraw_outcome.append("refused")

    def do_review() -> None:
        barrier.wait()
        db_execute("update feedback_submission set status = 'reviewed' where id = %s", (sid,))

    threads = [threading.Thread(target=do_withdraw), threading.Thread(target=do_review)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    remaining = db_rows("select status from feedback_submission where id = %s", (sid,))
    (outcome,) = withdraw_outcome
    if outcome == "withdrawn":
        assert remaining == [], "withdrawn means the row is gone"
    else:
        assert [r["status"] for r in remaining] == ["reviewed"], "refused means it moved"
    db_execute("delete from feedback_submission where id = %s", (sid,), bypass_triggers=True)
    return outcome


def test_concurrent_status_change_and_withdraw_exactly_one_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(monkeypatch)
    with committed_feedback_world("fb-race") as world:
        buyer = world.member(MemberRole.buyer)
        outcomes = {_race_withdraw_against_review(harness, buyer) for _ in range(12)}
        assert outcomes <= {"withdrawn", "refused"}
