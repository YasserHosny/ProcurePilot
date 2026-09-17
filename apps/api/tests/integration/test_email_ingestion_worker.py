from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.modules.ingestion import orchestrator as orchestrator_module
from procurepilot_api.workers import email_ingestion_worker
from procurepilot_api.workers.email_ingestion_worker import (
    _claim_pending_jobs,
    tick,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class _FakeBucket:
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        downloads: dict[str, bytes] | None = None,
    ) -> None:
        self._uploads = uploads
        self._downloads = downloads or {}

    def upload(self, path: str, content: bytes, options: dict[str, str]) -> None:
        self._uploads.append((path, content, options))

    def download(self, path: str) -> bytes:
        if path not in self._downloads:
            raise RuntimeError(f"Storage path not found: {path}")
        return self._downloads[path]


class _FakeStorage:
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        downloads: dict[str, bytes] | None = None,
    ) -> None:
        self._uploads = uploads
        self._downloads = downloads or {}

    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket(self._uploads, self._downloads)


class _FakeSupabaseClient:
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        downloads: dict[str, bytes] | None = None,
    ) -> None:
        self.storage = _FakeStorage(uploads, downloads)


def _patch_storage_and_queue(
    monkeypatch: pytest.MonkeyPatch,
    downloads: dict[str, bytes] | None = None,
) -> tuple[list[tuple[str, bytes, dict[str, str]]], list[dict[str, object]]]:
    uploads: list[tuple[str, bytes, dict[str, str]]] = []
    enqueued: list[dict[str, object]] = []

    def _fake_client_factory(*_a: object, **_k: object) -> _FakeSupabaseClient:
        return _FakeSupabaseClient(uploads, downloads)

    monkeypatch.setattr(
        email_ingestion_worker,
        "create_client",
        _fake_client_factory,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "create_client",
        _fake_client_factory,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_enqueue_extraction",
        lambda _settings, **kwargs: enqueued.append(kwargs),
    )
    return uploads, enqueued


def _seed_email_config(tenant_id: UUID, created_by: UUID) -> None:
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tenant_email_config (tenant_id, forwarding_address, created_by)
                values (%s, %s, %s)
                """,
                (tenant_id, f"{tenant_id}@ingest.procurepilot.local", created_by),
            )
        conn.commit()


def _build_email(
    *,
    from_addr: str,
    message_id: str,
    subject: str = "Quotation",
    attachment: bytes | None = b"%PDF-1.4 fake pdf",
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = "buyer@ingest.procurepilot.local"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg.set_content("Please find attached our latest quotation.")
    if attachment is not None:
        msg.add_attachment(attachment, maintype="application", subtype="pdf", filename="q.pdf")
    return msg.as_bytes()


def _insert_email_job(
    tenant_id: UUID,
    *,
    payload: dict[str, object] | None = None,
    status: str = "pending",
    attempts: int = 0,
    max_attempts: int = 3,
    locked_by: str | None = None,
    locked_at: datetime | None = None,
) -> UUID:
    job_id = uuid4()
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into ingestion_jobs
                  (id, tenant_id, job_type, status, payload, attempts, max_attempts,
                   locked_by, locked_at)
                values (%s, %s, 'email_ingest', %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    tenant_id,
                    status,
                    Jsonb(payload if payload is not None else {}),
                    attempts,
                    max_attempts,
                    locked_by,
                    locked_at,
                ),
            )
        conn.commit()
    return job_id


def test_claim_pending_jobs_claims_and_updates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_for_test_db(monkeypatch)
    with committed_smart_context("email-worker-claim") as context:
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/test1.eml"
        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="pending",
            attempts=0,
            max_attempts=3,
        )

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            claimed = _claim_pending_jobs(conn, limit=10)
            conn.commit()

        matched = [j for j in claimed if j["id"] == job_id]
        assert len(matched) == 1
        claimed_job = matched[0]

        # Assert returned job fields match what was inserted
        assert claimed_job["tenant_id"] == context.workspace.tenant_id
        assert claimed_job["job_type"] == "email_ingest"
        assert claimed_job["payload"] == {"raw_email_path": raw_email_path}
        assert claimed_job["attempts"] == 0
        assert claimed_job["max_attempts"] == 3

        # Assert database status is now 'processing'
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                db_row = cur.fetchone()

        assert db_row is not None
        assert db_row["status"] == "processing"
        assert db_row["locked_by"] == "email_ingestion_worker"
        assert db_row["locked_at"] is not None


def test_concurrency_skip_locked_prevents_duplicate_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_for_test_db(monkeypatch)
    with committed_smart_context("email-worker-concurrency") as context:
        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": "tenants/x/raw.eml"},
            status="pending",
        )

        conn_a = psycopg.connect(TEST_DATABASE_URL or "")
        conn_b = psycopg.connect(TEST_DATABASE_URL or "")
        try:
            # Connection A starts transaction and runs claim query without committing yet
            claimed_a = _claim_pending_jobs(conn_a, limit=10)
            assert any(j["id"] == job_id for j in claimed_a)

            # Connection B starts transaction and runs the exact same claim query while
            # connection A is still uncommitted
            claimed_b = _claim_pending_jobs(conn_b, limit=10)
            # The row locked by connection A must be skipped by B via FOR UPDATE SKIP LOCKED
            assert not any(j["id"] == job_id for j in claimed_b)
            assert claimed_b == []

            # Now commit connection A
            conn_a.commit()
            conn_b.rollback()
        finally:
            conn_a.close()
            conn_b.close()

        # Verify the database shows the job is claimed
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select status, locked_by from ingestion_jobs where id = %s", (job_id,))
                row = cur.fetchone()
        assert row is not None
        assert row["status"] == "processing"
        assert row["locked_by"] == "email_ingestion_worker"


def test_tick_success_path_creates_document_quotation_and_extraction_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)

    with committed_smart_context("email-worker-success", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        raw_email = _build_email(from_addr="sales@acme.com", message_id="<worker-success@acme.com>")
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/worker-success.eml"
        uploads, enqueued = _patch_storage_and_queue(
            monkeypatch, downloads={raw_email_path: raw_email}
        )

        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="pending",
        )

        stats = tick(settings)

        assert stats["claimed"] == 1
        assert stats["completed"] == 1
        assert len(uploads) == 1
        assert len(enqueued) == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                job_row = cur.fetchone()
                cur.execute(
                    "select * from ingestion_email_log where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                log_row = cur.fetchone()
                cur.execute(
                    "select * from quotation where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                quotation_row = cur.fetchone()
                cur.execute(
                    "select * from document where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                doc_row = cur.fetchone()
                cur.execute(
                    "select * from extraction_job where quotation_id = %s",
                    (quotation_row["id"],),
                )
                extraction_job_row = cur.fetchone()

        assert job_row is not None
        assert job_row["status"] == "completed"
        assert job_row["completed_at"] is not None
        assert job_row["attempts"] == 0

        assert log_row is not None
        assert log_row["status"] == "completed"
        assert log_row["supplier_id"] == supplier_id
        assert log_row["match_method"] == "domain"
        assert log_row["quotation_id"] == quotation_row["id"]

        assert quotation_row is not None
        assert quotation_row["source"] == "email"
        assert quotation_row["supplier_id"] == supplier_id
        assert quotation_row["document_id"] == doc_row["id"]
        assert quotation_row["ingestion_email_id"] == log_row["id"]

        assert doc_row is not None
        assert doc_row["source_channel"] == "email"
        assert doc_row["status"] == "uploaded"

        assert extraction_job_row is not None
        assert extraction_job_row["status"] == "queued"


def test_failure_retry_and_terminal_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("email-worker-retry") as context:
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/missing.eml"
        # Provide empty downloads map so downloading raw email raises
        _patch_storage_and_queue(monkeypatch, downloads={})

        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="pending",
            attempts=0,
            max_attempts=3,
        )

        def _get_job() -> dict[str, object]:
            with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                    row = cur.fetchone()
            assert row is not None
            return dict(row)

        # Attempt 1: fails, reverts to pending with attempts = 1
        stats1 = tick(settings)
        assert stats1["claimed"] == 1
        assert stats1["failed"] == 1

        job1 = _get_job()
        assert job1["status"] == "pending"
        assert job1["attempts"] == 1
        assert job1["locked_by"] is None
        assert job1["locked_at"] is None
        assert job1["completed_at"] is None
        assert job1["last_error"] is not None

        # Attempt 2: fails again, reverts to pending with attempts = 2
        stats2 = tick(settings)
        assert stats2["claimed"] == 1
        assert stats2["failed"] == 1

        job2 = _get_job()
        assert job2["status"] == "pending"
        assert job2["attempts"] == 2
        assert job2["locked_by"] is None
        assert job2["locked_at"] is None
        assert job2["completed_at"] is None

        # Attempt 3: fails third time, reaches max_attempts = 3, becomes terminal failed
        stats3 = tick(settings)
        assert stats3["claimed"] == 1
        assert stats3["failed"] == 1

        job3 = _get_job()
        assert job3["status"] == "failed"
        assert job3["attempts"] == 3
        assert job3["completed_at"] is not None

        # Attempt 4: terminal failed job is ignored, never retrying a fourth time
        stats4 = tick(settings)
        assert stats4["claimed"] == 0
        assert stats4["failed"] == 0

        job4 = _get_job()
        assert job4["status"] == "failed"
        assert job4["attempts"] == 3


def test_tenant_id_discipline_read_from_job_row_not_untrusted_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)

    with committed_smart_context("email-worker-tenant-disc", supplier_count=1) as context:
        real_tenant_id = context.workspace.tenant_id
        supplier_id = context.supplier_ids[0]
        _seed_email_config(real_tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        fake_untrusted_tenant_id = uuid4()
        raw_email_wrong = _build_email(
            from_addr="sales@acme.com", message_id="<worker-disc-wrong@acme.com>"
        )
        raw_email_none = _build_email(
            from_addr="sales@acme.com", message_id="<worker-disc-none@acme.com>"
        )
        path_wrong = f"tenants/{real_tenant_id}/raw/worker-disc-wrong.eml"
        path_none = f"tenants/{real_tenant_id}/raw/worker-disc-none.eml"
        _patch_storage_and_queue(
            monkeypatch,
            downloads={path_wrong: raw_email_wrong, path_none: raw_email_none},
        )

        captured_calls: list[dict[str, object]] = []
        real_process_inbound_email = orchestrator_module.process_inbound_email

        def _spy_process_inbound_email(
            settings_arg: object,
            *,
            tenant_id: UUID,
            raw_email_bytes: bytes,
            raw_email_ref: str | None = None,
        ) -> dict[str, object]:
            captured_calls.append({"tenant_id": tenant_id, "raw_email_ref": raw_email_ref})
            return real_process_inbound_email(
                settings_arg,  # type: ignore[arg-type]
                tenant_id=tenant_id,
                raw_email_bytes=raw_email_bytes,
                raw_email_ref=raw_email_ref,
            )

        monkeypatch.setattr(
            email_ingestion_worker, "process_inbound_email", _spy_process_inbound_email
        )

        # Case 1: Payload carries a deliberately wrong tenant identifier
        job_id_wrong = _insert_email_job(
            real_tenant_id,
            payload={
                "raw_email_path": path_wrong,
                "tenant_id": str(fake_untrusted_tenant_id),
            },
            status="pending",
        )
        # Case 2: Payload carries NO tenant identifier at all
        job_id_none = _insert_email_job(
            real_tenant_id,
            payload={
                "raw_email_path": path_none,
            },
            status="pending",
        )

        stats = tick(settings)

        assert stats["claimed"] == 2
        assert stats["completed"] == 2

        # Assert process_inbound_email was invoked with real row tenant_id in both cases
        assert len(captured_calls) == 2
        for call in captured_calls:
            assert call["tenant_id"] == real_tenant_id
            assert call["tenant_id"] != fake_untrusted_tenant_id

        # Assert database records are associated with the real row tenant_id and
        # NOT the fake tenant_id
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status from ingestion_jobs where id in (%s, %s)",
                    (job_id_wrong, job_id_none),
                )
                job_statuses = [r["status"] for r in cur.fetchall()]
                cur.execute(
                    "select count(*) as cnt from quotation where tenant_id = %s",
                    (real_tenant_id,),
                )
                real_quotations = cur.fetchone()["cnt"]
                cur.execute(
                    "select count(*) as cnt from quotation where tenant_id = %s",
                    (fake_untrusted_tenant_id,),
                )
                fake_quotations = cur.fetchone()["cnt"]
                cur.execute(
                    "select count(*) as cnt from document where tenant_id = %s",
                    (real_tenant_id,),
                )
                real_docs = cur.fetchone()["cnt"]
                cur.execute(
                    "select count(*) as cnt from document where tenant_id = %s",
                    (fake_untrusted_tenant_id,),
                )
                fake_docs = cur.fetchone()["cnt"]

        assert job_statuses == ["completed", "completed"]
        assert real_quotations == 2
        assert fake_quotations == 0
        assert real_docs == 2
        assert fake_docs == 0


def test_stale_processing_job_reclaimed_and_processed_on_tick(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = settings_for_test_db(monkeypatch)

    with committed_smart_context("email-worker-stale-reclaim", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        raw_email = _build_email(
            from_addr="sales@acme.com", message_id="<worker-stale@acme.com>"
        )
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/worker-stale.eml"
        uploads, enqueued = _patch_storage_and_queue(
            monkeypatch, downloads={raw_email_path: raw_email}
        )

        stale_time = datetime.now(UTC) - timedelta(
            seconds=settings.email_ingestion_stale_lock_seconds + 60
        )
        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="processing",
            attempts=0,
            max_attempts=3,
            locked_by="dead_worker",
            locked_at=stale_time,
        )

        with caplog.at_level(logging.WARNING):
            stats = tick(settings)

        assert stats["claimed"] == 1
        assert stats["completed"] == 1
        assert len(uploads) == 1
        assert len(enqueued) == 1
        assert "claimed: reclaimed stale lock" in caplog.text

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                job_row = cur.fetchone()

        assert job_row is not None
        assert job_row["status"] == "completed"
        assert job_row["completed_at"] is not None
        # Attempts was incremented to 1 during the stale reclaim
        assert job_row["attempts"] == 1


def test_recent_processing_job_not_reclaimed_by_concurrent_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)

    with committed_smart_context("email-worker-recent-lock") as context:
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/worker-recent.eml"
        recent_time = datetime.now(UTC) - timedelta(seconds=10)
        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="processing",
            attempts=0,
            max_attempts=3,
            locked_by="in_flight_worker",
            locked_at=recent_time,
        )

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            claimed = _claim_pending_jobs(conn, settings=settings, limit=10)
            conn.commit()

        assert not any(j["id"] == job_id for j in claimed)

        # Also verify tick() does not claim or touch the in-flight job
        stats = tick(settings)
        assert stats["claimed"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                job_row = cur.fetchone()

        assert job_row is not None
        assert job_row["status"] == "processing"
        assert job_row["attempts"] == 0
        assert job_row["locked_by"] == "in_flight_worker"
        assert job_row["completed_at"] is None


def test_stale_job_exceeding_max_attempts_marked_failed_directly(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = settings_for_test_db(monkeypatch)

    with committed_smart_context("email-worker-stale-max-attempts") as context:
        raw_email_path = f"tenants/{context.workspace.tenant_id}/raw/worker-exhausted.eml"
        stale_time = datetime.now(UTC) - timedelta(
            seconds=settings.email_ingestion_stale_lock_seconds + 60
        )
        # Job already at 2 attempts with max_attempts = 3.
        # Reclaim increment (2 + 1 = 3) reaches max_attempts.
        job_id = _insert_email_job(
            context.workspace.tenant_id,
            payload={"raw_email_path": raw_email_path},
            status="processing",
            attempts=2,
            max_attempts=3,
            locked_by="dead_worker",
            locked_at=stale_time,
        )

        with caplog.at_level(logging.WARNING):
            stats = tick(settings)

        # Job is marked failed directly in claim query rather than claimed into processing
        assert stats["claimed"] == 0
        assert stats["failed"] == 0

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("select * from ingestion_jobs where id = %s", (job_id,))
                job_row = cur.fetchone()

        assert job_row is not None
        assert job_row["status"] == "failed"
        assert job_row["attempts"] == 3
        assert job_row["completed_at"] is not None
        assert job_row["locked_by"] is None
        assert job_row["locked_at"] is None
        assert job_row["last_error"] is not None
        assert "stale lock" in job_row["last_error"].lower()

        # Subsequent tick() does not touch terminal-failed job
        stats2 = tick(settings)
        assert stats2["claimed"] == 0

