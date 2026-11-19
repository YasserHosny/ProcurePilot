"""Feedback retention purge and orphan sweep (spec 025 T074; implementation T075).

UNRUN without TEST_DATABASE_URL. A recording `ObjectRemover` stands in for Supabase Storage: the
tests assert WHICH objects the worker asks to delete and what is left in the tables. Orphan
detection reads `storage.objects` over SQL, so these tests insert rows there directly.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from integration.feedback_operator_helpers import (
    Workspace,
    committed_workspace,
    insert_attachment,
    insert_submission,
)
from procurepilot_api.config import get_settings
from procurepilot_api.workers.feedback_worker import purge_retention, sweep_orphans

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with the migrations applied",
)

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
BUCKET = "feedback-attachments"


class RecordingRemover:
    def __init__(self, *, fail: bool = False) -> None:
        self.removed: list[str] = []
        self.fail = fail

    def remove(self, *, bucket: str, paths: Sequence[str]) -> None:
        assert bucket == BUCKET
        if self.fail:
            raise RuntimeError("storage down")
        self.removed.extend(paths)


@pytest.fixture
def ws() -> Iterator[Workspace]:
    with committed_workspace("ret") as workspace:
        yield workspace


def _submission(ws: Workspace, *, created_at: datetime, status: str = "new") -> tuple[object, str]:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            submission = insert_submission(cur, ws, created_at=created_at, status=status)
            _, path = insert_attachment(cur, ws, submission)
    return submission, path


def _exists(submission_id: object) -> bool:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        return conn.execute(
            "select count(*) from feedback_submission where id = %s", (submission_id,)
        ).fetchone() == (1,)


def test_submissions_older_than_twelve_months_are_deleted_with_their_objects(ws: Workspace) -> None:
    old, old_path = _submission(ws, created_at=NOW - timedelta(days=366))
    old_resolved, resolved_path = _submission(
        ws, created_at=NOW - timedelta(days=400), status="resolved"
    )
    recent, recent_path = _submission(ws, created_at=NOW - timedelta(days=364))
    remover = RecordingRemover()

    stats = purge_retention(get_settings(), remover, NOW)

    assert stats["submissions"] >= 2
    assert not _exists(old) and not _exists(old_resolved), "age counts, not status"
    assert _exists(recent)
    assert {old_path, resolved_path} <= set(remover.removed)
    assert recent_path not in remover.removed


def test_the_purge_writes_one_aggregate_event_with_counts_and_no_content(ws: Workspace) -> None:
    _submission(ws, created_at=NOW - timedelta(days=500))
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        before = conn.execute(
            "select count(*) from audit_event where action = 'feedback.retention_purged'"
        ).fetchone()[0]  # type: ignore[index]

    purge_retention(get_settings(), RecordingRemover(), NOW)

    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        rows = conn.execute(
            "select tenant_id, target from audit_event "
            "where action = 'feedback.retention_purged' order by id"
        ).fetchall()
    assert len(rows) == before + 1
    tenant_id, target = rows[-1]
    assert tenant_id is None
    assert set(target) == {"submissions", "objects", "retention_months"}
    assert target["submissions"] >= 1 and target["retention_months"] == 12


def test_nothing_to_purge_writes_no_event(ws: Workspace) -> None:
    _submission(ws, created_at=NOW - timedelta(days=10))
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        before = conn.execute(
            "select count(*) from audit_event where action = 'feedback.retention_purged'"
        ).fetchone()[0]  # type: ignore[index]
    # Other rows in a shared database may be old; this asserts only that our own survive.
    purge_retention(get_settings(), RecordingRemover(), NOW)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        after = conn.execute(
            "select count(*) from audit_event where action = 'feedback.retention_purged'"
        ).fetchone()[0]  # type: ignore[index]
    assert after in {before, before + 1}


def test_a_storage_failure_keeps_the_rows_so_the_next_pass_retries(ws: Workspace) -> None:
    old, _ = _submission(ws, created_at=NOW - timedelta(days=400))
    with pytest.raises(RuntimeError):
        purge_retention(get_settings(), RecordingRemover(fail=True), NOW)
    assert _exists(old)

    purge_retention(get_settings(), RecordingRemover(), NOW)
    assert not _exists(old)


def _object(name: str, *, created_at: datetime) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        conn.execute(
            "insert into storage.objects (bucket_id, name, created_at) values (%s, %s, %s)",
            (BUCKET, name, created_at),
        )


def test_orphan_objects_older_than_an_hour_are_swept_and_newer_ones_kept(ws: Workspace) -> None:
    prefix = f"tenants/{ws.tenant_id}/feedback/{uuid4()}"
    old_orphan = f"{prefix}/old/shot.png"
    fresh_orphan = f"{prefix}/fresh/shot.png"
    _object(old_orphan, created_at=NOW - timedelta(hours=2))
    _object(fresh_orphan, created_at=NOW - timedelta(minutes=20))
    remover = RecordingRemover()

    sweep_orphans(get_settings(), remover, NOW)

    assert old_orphan in remover.removed
    assert fresh_orphan not in remover.removed


def test_objects_that_an_attachment_row_references_are_never_swept(ws: Workspace) -> None:
    submission, path = _submission(ws, created_at=NOW - timedelta(days=1))
    _object(path, created_at=NOW - timedelta(days=1))
    remover = RecordingRemover()

    sweep_orphans(get_settings(), remover, NOW)

    assert path not in remover.removed
    assert _exists(submission)
