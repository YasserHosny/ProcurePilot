from __future__ import annotations

from email.message import EmailMessage
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.modules.ingestion import orchestrator as orchestrator_module

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class _FakeBucket:
    def __init__(self, uploads: list[tuple[str, bytes, dict[str, str]]]) -> None:
        self._uploads = uploads

    def upload(self, path: str, content: bytes, options: dict[str, str]) -> None:
        self._uploads.append((path, content, options))


class _FakeStorage:
    def __init__(self, uploads: list[tuple[str, bytes, dict[str, str]]]) -> None:
        self._uploads = uploads

    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket(self._uploads)


class _FakeSupabaseClient:
    def __init__(self, uploads: list[tuple[str, bytes, dict[str, str]]]) -> None:
        self.storage = _FakeStorage(uploads)


def _patch_storage_and_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, bytes, dict[str, str]]], list[dict[str, object]]]:
    uploads: list[tuple[str, bytes, dict[str, str]]] = []
    enqueued: list[dict[str, object]] = []
    monkeypatch.setattr(
        orchestrator_module, "create_client", lambda *_a, **_k: _FakeSupabaseClient(uploads)
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_enqueue_extraction",
        lambda settings, **kwargs: enqueued.append(kwargs),
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


def test_matched_supplier_email_creates_document_quotation_and_extraction_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    uploads, enqueued = _patch_storage_and_queue(monkeypatch)

    with committed_smart_context("ingestion-orchestrator-matched", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        raw_email = _build_email(from_addr="sales@acme.com", message_id="<msg-1@acme.com>")

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref="tenants/x/raw-email/1.eml",
        )

        assert result["status"] == "completed"
        assert result["supplier_id"] == str(supplier_id)
        assert result["match_method"] == "domain"
        assert len(uploads) == 1
        assert len(enqueued) == 1

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select * from ingestion_email_log where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                log_row = cur.fetchone()
                cur.execute(
                    "select * from quotation where id = %s", (UUID(result["quotation_id"]),)
                )
                quotation_row = cur.fetchone()
                cur.execute(
                    "select status from extraction_job where quotation_id = %s",
                    (UUID(result["quotation_id"]),),
                )
                job_row = cur.fetchone()

        assert log_row["status"] == "completed"
        assert log_row["supplier_id"] == supplier_id
        assert log_row["match_method"] == "domain"
        assert str(log_row["quotation_id"]) == result["quotation_id"]
        assert quotation_row["source"] == "email"
        assert quotation_row["supplier_id"] == supplier_id
        assert str(quotation_row["ingestion_email_id"]) == str(log_row["id"])
        assert job_row["status"] == "queued"


def test_unmatched_supplier_email_creates_a_review_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)

    with committed_smart_context("ingestion-orchestrator-unmatched", supplier_count=1) as context:
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        raw_email = _build_email(from_addr="rep@unknown-domain.test", message_id="<msg-2@x>")

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref=None,
        )

        assert result["status"] == "completed"
        assert result["supplier_id"] is None
        assert result["match_method"] is None

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select * from review_task where quotation_id = %s",
                    (UUID(result["quotation_id"]),),
                )
                task_row = cur.fetchone()

        assert task_row is not None
        assert task_row["status"] == "open"
        assert task_row["reason"] == "review_required"


def test_no_attachment_email_stores_body_text_as_the_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    uploads, _ = _patch_storage_and_queue(monkeypatch)

    with committed_smart_context("ingestion-orchestrator-textonly", supplier_count=1) as context:
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        raw_email = _build_email(
            from_addr="rep@nowhere.test", message_id="<msg-3@x>", attachment=None
        )

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref=None,
        )

        assert result["status"] == "completed"
        assert uploads[0][2]["content-type"] == "text/plain"

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select mime_type from document where id = %s",
                    (UUID(result["document_id"]),),
                )
                document_row = cur.fetchone()

        assert document_row["mime_type"] == "text/plain"


def test_duplicate_message_id_is_skipped_without_creating_a_second_quotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)

    with committed_smart_context("ingestion-orchestrator-dup", supplier_count=1) as context:
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        raw_email = _build_email(from_addr="rep@nowhere.test", message_id="<dup-msg@x>")

        first = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref=None,
        )
        second = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref=None,
        )

        assert first["status"] == "completed"
        assert second == {"status": "duplicate", "message_id": "dup-msg@x"}

        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from ingestion_email_log where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                count = cur.fetchone()[0]
        assert count == 1
