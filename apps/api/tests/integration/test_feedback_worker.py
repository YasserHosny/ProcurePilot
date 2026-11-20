"""Feedback worker, digest job (spec 025 T061, FR-024). UNRUN without TEST_DATABASE_URL.

Real database, `FakeMailer` for mail. The database may hold other operators and feedback from
other runs, so every assertion filters by this test's own operator address and workspaces.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from integration.feedback_operator_helpers import (
    Workspace,
    committed_workspace,
    grant_operator,
    insert_submission,
)
from procurepilot_api.config import get_settings
from procurepilot_api.shared.mailer import FakeMailer, FakeMessage
from procurepilot_api.workers.feedback_worker import DIGEST_SETTLE, run_digest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)


class _Env:
    def __init__(self, operator: Workspace, source: Workspace, operator_email: str) -> None:
        self.operator = operator
        self.source = source
        self.operator_email = operator_email
        self.mailer = FakeMailer()

    def sent_to_operator(self) -> list[FakeMessage]:
        return [m for m in self.mailer.sent_messages if m.to == self.operator_email]

    def run(self, now: datetime = NOW) -> dict[str, int]:
        return run_digest(get_settings(), self.mailer, now)

    def watermark(self) -> datetime | None:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            row = conn.execute(
                "select digest_last_sent_at from platform_operator where user_id = %s",
                (self.operator.user_id,),
            ).fetchone()
        return row[0] if row else None

    def set_operator(self, **columns: object) -> None:
        sets = ", ".join(f"{name} = %s" for name in columns)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            conn.execute(
                f"update platform_operator set {sets} where user_id = %s",  # noqa: S608
                (*columns.values(), self.operator.user_id),
            )

    def submit(self, text: str, *, at: datetime, category: str | None = "bug") -> None:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                insert_submission(cur, self.source, text=text, category=category, created_at=at)


@pytest.fixture
def env() -> Iterator[_Env]:
    FakeMailer.clear()
    with committed_workspace("digop") as operator, committed_workspace("digsrc") as source:
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                grant_operator(cur, operator, digest_opt_in=True)
            row = conn.execute(
                "select email from platform_operator where user_id = %s", (operator.user_id,)
            ).fetchone()
        assert row is not None
        environment = _Env(operator, source, row[0])
        # A watermark a day back, as if yesterday's digest went out.
        environment.set_operator(digest_last_sent_at=NOW - timedelta(days=1))
        yield environment
    FakeMailer.clear()


def test_opted_in_operator_gets_one_digest_with_the_expected_fields(env: _Env) -> None:
    env.submit("the compare page hangs", at=NOW - timedelta(hours=3), category="bug")

    stats = env.run()

    assert stats["sent"] >= 1
    (message,) = env.sent_to_operator()
    for body in (message.body, message.html or ""):
        assert f"{env.source.label} Ltd" in body
        assert "the compare page hangs" in body
        assert "/platform/feedback" in body
    assert "Bug" in message.body
    assert env.watermark() == NOW - DIGEST_SETTLE


def test_a_submission_inside_the_settle_window_waits_for_the_next_digest(env: _Env) -> None:
    """Debate-review F4 (2026-11-20): created_at is when the submit transaction began, and that
    transaction stays open while files upload. A digest that took 'everything up to now' could
    move its watermark past a row that commits a moment later, and that row would never be sent.
    So the digest takes rows older than DIGEST_SETTLE and moves the watermark only that far."""
    env.submit("settled report", at=NOW - timedelta(hours=1))
    env.submit("still uploading", at=NOW - DIGEST_SETTLE / 2)

    env.run()
    (first,) = env.sent_to_operator()
    assert "settled report" in first.body
    assert "still uploading" not in first.body

    env.run(NOW + timedelta(days=1))
    second = env.sent_to_operator()[-1]
    assert "still uploading" in second.body
    assert "settled report" not in second.body


def test_the_digest_never_contains_an_email_address_or_attachment_reference(env: _Env) -> None:
    env.submit("contact me on ceo@customer.example please", at=NOW - timedelta(hours=1))
    env.run()
    (message,) = env.sent_to_operator()
    submitter_email = f"{env.source.label.lower()}-submitter@example.test"
    for body in (message.subject, message.body, message.html or ""):
        assert submitter_email not in body
        assert "ceo@customer.example" not in body
        assert "tenants/" not in body  # storage paths


def test_only_feedback_newer_than_the_watermark_is_included(env: _Env) -> None:
    env.submit("already reported yesterday", at=NOW - timedelta(days=2))
    env.submit("fresh this morning", at=NOW - timedelta(hours=2))
    env.run()
    (message,) = env.sent_to_operator()
    assert "fresh this morning" in message.body
    assert "already reported yesterday" not in message.body


def test_no_email_on_a_day_with_nothing_new(env: _Env) -> None:
    env.submit("old news", at=NOW - timedelta(days=3))
    env.run()
    assert env.sent_to_operator() == []
    assert env.watermark() == NOW - timedelta(days=1), "an empty day must not move the watermark"


def test_a_midnight_digest_hour_still_sends_at_most_one_email_that_day(env: _Env) -> None:
    """Codex on #602: with FEEDBACK_DIGEST_HOUR_UTC=0, a send at 00:05 would store a settled
    watermark dated yesterday, and the once-a-day guard (which reads that date) would let a second
    send through. The digest waits until the settle window no longer crosses midnight."""
    settings = get_settings().model_copy(update={"feedback_digest_hour_utc": 0})
    midnight = NOW.replace(hour=0, minute=0)
    env.submit("late last night", at=midnight - timedelta(minutes=20))

    assert run_digest(settings, env.mailer, midnight + timedelta(minutes=5))["sent"] == 0
    run_digest(settings, env.mailer, midnight + timedelta(minutes=15))
    env.submit("just after midnight", at=midnight + timedelta(minutes=2))
    run_digest(settings, env.mailer, midnight + timedelta(minutes=30))

    (only,) = env.sent_to_operator()
    assert "late last night" in only.body


def test_at_most_one_digest_per_day(env: _Env) -> None:
    env.submit("first", at=NOW - timedelta(hours=4))
    env.run()
    env.submit("second", at=NOW + timedelta(hours=1))
    env.run(NOW + timedelta(hours=2))
    assert len(env.sent_to_operator()) == 1

    # The next day the later item goes out.
    env.run(NOW + timedelta(days=1))
    messages = env.sent_to_operator()
    assert len(messages) == 2
    assert "second" in messages[1].body and "first" not in messages[1].body


def test_nothing_is_sent_before_the_configured_hour(env: _Env) -> None:
    env.submit("early", at=NOW.replace(hour=0, minute=30))
    stats = env.run(NOW.replace(hour=0, minute=45))
    assert env.sent_to_operator() == []
    assert stats["sent"] == 0


def test_operators_who_did_not_opt_in_or_were_revoked_get_nothing(env: _Env) -> None:
    env.submit("something", at=NOW - timedelta(hours=1))

    env.set_operator(digest_opt_in=False)
    env.run()
    assert env.sent_to_operator() == []

    env.set_operator(digest_opt_in=True, revoked_at=NOW)
    env.run()
    assert env.sent_to_operator() == []


def test_arabic_operator_gets_an_arabic_right_to_left_digest(env: _Env) -> None:
    env.set_operator(digest_locale="ar")
    env.submit("الصفحة بطيئة", at=NOW - timedelta(hours=1), category="idea")
    env.run()
    (message,) = env.sent_to_operator()
    assert 'dir="rtl"' in (message.html or "")
    assert "فكرة" in message.body
    assert "emails.feedbackDigest" not in message.body


def test_a_failed_send_keeps_the_watermark_so_the_next_pass_retries(env: _Env) -> None:
    env.submit("will retry", at=NOW - timedelta(hours=1))

    class Broken(FakeMailer):
        def send(self, **_: object) -> object:  # type: ignore[override]
            raise RuntimeError("smtp down")

    stats = run_digest(get_settings(), Broken(), NOW)
    assert stats["failed"] >= 1
    assert env.watermark() == NOW - timedelta(days=1)

    env.run()
    assert len(env.sent_to_operator()) == 1
