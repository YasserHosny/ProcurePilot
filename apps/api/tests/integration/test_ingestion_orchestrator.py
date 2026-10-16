from __future__ import annotations

from email.message import EmailMessage
from uuid import UUID, uuid4

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
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        fail_on_path_pattern: str | None = None,
    ) -> None:
        self._uploads = uploads
        self._fail_on_path_pattern = fail_on_path_pattern

    def upload(self, path: str, content: bytes, options: dict[str, str]) -> None:
        if self._fail_on_path_pattern and self._fail_on_path_pattern in path:
            raise RuntimeError(f"Storage upload failed for {path}")
        self._uploads.append((path, content, options))


class _FakeStorage:
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        fail_on_path_pattern: str | None = None,
    ) -> None:
        self._uploads = uploads
        self._fail_on_path_pattern = fail_on_path_pattern

    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket(self._uploads, self._fail_on_path_pattern)


class _FakeSupabaseClient:
    def __init__(
        self,
        uploads: list[tuple[str, bytes, dict[str, str]]],
        fail_on_path_pattern: str | None = None,
    ) -> None:
        self.storage = _FakeStorage(uploads, fail_on_path_pattern)


def _patch_storage_and_queue(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_on_path_pattern: str | None = None,
) -> tuple[list[tuple[str, bytes, dict[str, str]]], list[dict[str, object]]]:
    uploads: list[tuple[str, bytes, dict[str, str]]] = []
    enqueued: list[dict[str, object]] = []
    monkeypatch.setattr(
        orchestrator_module,
        "create_client",
        lambda *_a, **_k: _FakeSupabaseClient(uploads, fail_on_path_pattern),
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
    attachments: list[tuple[bytes, str]] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = "buyer@ingest.procurepilot.local"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg.set_content("Please find attached our latest quotation.")
    if attachments is not None:
        for content, filename in attachments:
            msg.add_attachment(content, maintype="application", subtype="pdf", filename=filename)
    elif attachment is not None:
        msg.add_attachment(attachment, maintype="application", subtype="pdf", filename="q.pdf")
    return msg.as_bytes()


def _build_rfq_reply(
    *, from_addr: str, message_id: str, in_reply_to: str, references: list[str] | None = None
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = "buyer@ingest.procurepilot.local"
    msg["Subject"] = "Quotation"
    msg["Message-ID"] = message_id
    msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)
    msg.set_content("Please find attached our latest quotation.")
    msg.add_attachment(b"%PDF-1.4 quote", maintype="application", subtype="pdf", filename="q.pdf")
    return msg.as_bytes()


def _seed_rfq_recipient(tenant_id: UUID, supplier_id: UUID) -> tuple[UUID, str]:
    recipient_id = uuid4()
    idempotency_key = uuid4()
    message_id = f"<{uuid4()}@procurepilot.test>"
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into rfq (tenant_id, created_by_membership_id, status, needed_by_date,
                                 idempotency_key)
                values (%s, (select id from membership where tenant_id = %s limit 1),
                        'sent', current_date + 30, %s)
                returning id
                """,
                (tenant_id, tenant_id, idempotency_key),
            )
            rfq_id = cur.fetchone()[0]
            message_id = f"<{uuid4()}@procurepilot.test>"
            cur.execute(
                """
                insert into rfq_recipient (id, tenant_id, rfq_id, supplier_id, status,
                                           outbound_message_id)
                values (%s, %s, %s, %s, 'sent', %s)
                """,
                (recipient_id, tenant_id, rfq_id, supplier_id, message_id),
            )
        conn.commit()
    return recipient_id, message_id


def test_shared_address_rfq_replies_use_their_recipient_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)
    with committed_smart_context("ingestion-rfq-shared-address", supplier_count=2) as context:
        supplier_a, supplier_b = context.supplier_ids
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        recipient_a, message_a = _seed_rfq_recipient(context.workspace.tenant_id, supplier_a)
        recipient_b, message_b = _seed_rfq_recipient(context.workspace.tenant_id, supplier_b)

        results = []
        for suffix, supplier, recipient, rfq_message in (
            ("a", supplier_a, recipient_a, message_a),
            ("b", supplier_b, recipient_b, message_b),
        ):
            result = orchestrator_module.process_inbound_email(
                settings,
                tenant_id=context.workspace.tenant_id,
                raw_email_bytes=_build_rfq_reply(
                    from_addr="shared.sender@gmail.com",
                    message_id=f"<shared-{suffix}@gmail.com>",
                    in_reply_to=rfq_message,
                ),
                raw_email_ref=None,
            )
            assert result["supplier_id"] == str(supplier)
            assert result["match_method"] == "rfq_reply"
            results.append((result, recipient, supplier))

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                for result, recipient, supplier in results:
                    cur.execute(
                        "select supplier_id, match_method from ingestion_email_log "
                        "where quotation_id = %s",
                        (UUID(result["quotation_id"]),),
                    )
                    log_row = cur.fetchone()
                    cur.execute(
                        "select supplier_id from quotation where id = %s",
                        (UUID(result["quotation_id"]),),
                    )
                    quotation_row = cur.fetchone()
                    cur.execute(
                        "select quotation_id from rfq_response where rfq_recipient_id = %s",
                        (recipient,),
                    )
                    response_row = cur.fetchone()
                    assert log_row["supplier_id"] == supplier
                    assert log_row["match_method"] == "rfq_reply"
                    assert quotation_row["supplier_id"] == supplier
                    assert str(response_row["quotation_id"]) == result["quotation_id"]


def test_rfq_reply_overrides_conflicting_address_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)
    with committed_smart_context("ingestion-rfq-history-conflict", supplier_count=2) as context:
        supplier_a, supplier_b = context.supplier_ids
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        recipient_b, message_b = _seed_rfq_recipient(context.workspace.tenant_id, supplier_b)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into ingestion_email_log
                       (tenant_id, message_id, from_address, from_domain, status,
                        supplier_id, match_method)
                       values (%s, %s, %s, %s, 'completed', %s, 'manual')""",
                    (
                        context.workspace.tenant_id,
                        f"<{uuid4()}@gmail.com>",
                        "shared.sender@gmail.com",
                        "gmail.com",
                        supplier_a,
                    ),
                )
            conn.commit()

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=_build_rfq_reply(
                from_addr="shared.sender@gmail.com",
                message_id=f"<{uuid4()}@gmail.com>",
                in_reply_to=message_b,
            ),
            raw_email_ref=None,
        )
        assert result["supplier_id"] == str(supplier_b)
        assert result["match_method"] == "rfq_reply"
        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select supplier_id, match_method from ingestion_email_log "
                    "where quotation_id = %s",
                    (UUID(result["quotation_id"]),),
                )
                log_row = cur.fetchone()
                cur.execute(
                    "select supplier_id from quotation where id = %s",
                    (UUID(result["quotation_id"]),),
                )
                quotation_row = cur.fetchone()
                cur.execute(
                    "select quotation_id from rfq_response where rfq_recipient_id = %s",
                    (recipient_b,),
                )
                response_row = cur.fetchone()
        assert log_row["supplier_id"] == supplier_b
        assert log_row["match_method"] == "rfq_reply"
        assert quotation_row["supplier_id"] == supplier_b
        assert str(response_row["quotation_id"]) == result["quotation_id"]


def test_ambiguous_rfq_references_fall_back_without_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)
    with committed_smart_context("ingestion-rfq-ambiguous-references", supplier_count=2) as context:
        supplier_a, supplier_b = context.supplier_ids
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        recipient_a, message_a = _seed_rfq_recipient(context.workspace.tenant_id, supplier_a)
        recipient_b, message_b = _seed_rfq_recipient(context.workspace.tenant_id, supplier_b)

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=_build_rfq_reply(
                from_addr="ambiguous.sender@gmail.com",
                message_id=f"<{uuid4()}@gmail.com>",
                in_reply_to=f"<{uuid4()}@procurepilot.test>",
                references=[message_a, message_b],
            ),
            raw_email_ref=None,
        )

        assert result["match_method"] != "rfq_reply"
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from rfq_response where rfq_recipient_id in (%s, %s)",
                    (recipient_a, recipient_b),
                )
                response_count = cur.fetchone()[0]
        assert response_count == 0


def test_non_rfq_email_keeps_single_supplier_address_history_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    _patch_storage_and_queue(monkeypatch)
    with committed_smart_context("ingestion-non-rfq-address", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into ingestion_email_log
                       (tenant_id, message_id, from_address, from_domain, status,
                        supplier_id, match_method)
                       values (%s, %s, %s, %s, 'completed', %s, 'domain')""",
                    (
                        context.workspace.tenant_id,
                        f"<{uuid4()}@gmail.com>",
                        "known.sender@gmail.com",
                        "gmail.com",
                        supplier_id,
                    ),
                )
            conn.commit()

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=_build_email(
                from_addr="known.sender@gmail.com", message_id=f"<{uuid4()}@gmail.com>"
            ),
            raw_email_ref=None,
        )
        assert result["supplier_id"] == str(supplier_id)
        assert result["match_method"] == "address"
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from rfq_response where quotation_id = %s",
                    (UUID(result["quotation_id"]),),
                )
                assert cur.fetchone()[0] == 0


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


def test_multiple_attachments_stores_all_documents_but_extracts_only_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    uploads, enqueued = _patch_storage_and_queue(monkeypatch)

    with committed_smart_context("ingestion-orchestrator-multi-att", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        email_attachments = [
            (b"%PDF-1.4 quotation primary", "primary_quote.pdf"),
            (b"%PDF-1.4 spec sheet secondary", "spec_sheet.pdf"),
            (b"%PDF-1.4 terms conditions secondary", "terms.pdf"),
        ]
        raw_email = _build_email(
            from_addr="sales@acme.com",
            message_id="<multi-att-1@acme.com>",
            attachments=email_attachments,
        )

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref="tenants/x/raw-email/multi.eml",
        )

        assert result["status"] == "completed"
        # All 3 attachments uploaded to storage with distinct paths
        assert len(uploads) == 3
        uploaded_paths = [u[0] for u in uploads]
        assert any("primary_quote.pdf" in p for p in uploaded_paths)
        assert any("spec_sheet.pdf" in p for p in uploaded_paths)
        assert any("terms.pdf" in p for p in uploaded_paths)
        assert len(set(uploaded_paths)) == 3

        # Only one extraction job enqueued, for the primary document
        assert len(enqueued) == 1
        assert str(enqueued[0]["document_id"]) == result["document_id"]
        assert str(enqueued[0]["quotation_id"]) == result["quotation_id"]

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, storage_path, mime_type, source_channel, status, created_by
                    from document
                    where tenant_id = %s
                    order by created_at asc
                    """,
                    (context.workspace.tenant_id,),
                )
                doc_rows = cur.fetchall()

                cur.execute(
                    "select id, document_id from quotation where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                quotation_rows = cur.fetchall()

                cur.execute(
                    "select id, quotation_id, status from extraction_job where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                job_rows = cur.fetchall()

        # 3 document rows total (not 1)
        assert len(doc_rows) == 3
        assert {r["source_channel"] for r in doc_rows} == {"email"}
        assert {r["status"] for r in doc_rows} == {"uploaded"}
        assert {r["created_by"] for r in doc_rows} == {context.workspace.membership_id}

        # Only the first is referenced by quotation.document_id
        assert len(quotation_rows) == 1
        assert str(quotation_rows[0]["id"]) == result["quotation_id"]
        assert str(quotation_rows[0]["document_id"]) == result["document_id"]

        # Only one extraction_job row exists total (for the primary)
        assert len(job_rows) == 1
        assert str(job_rows[0]["quotation_id"]) == result["quotation_id"]
        assert job_rows[0]["status"] == "queued"


def test_secondary_attachment_upload_failure_does_not_abort_primary_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    uploads, enqueued = _patch_storage_and_queue(
        monkeypatch, fail_on_path_pattern="failing_sec.pdf"
    )

    with committed_smart_context("ingestion-orchestrator-sec-fail", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        _seed_email_config(context.workspace.tenant_id, context.workspace.membership_id)
        with psycopg.connect(TEST_DATABASE_URL or "") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update supplier set email_domains = %s where id = %s",
                    (["acme.com"], supplier_id),
                )
            conn.commit()

        email_attachments = [
            (b"%PDF-1.4 primary quote", "primary.pdf"),
            (b"%PDF-1.4 failing secondary", "failing_sec.pdf"),
            (b"%PDF-1.4 succeeding secondary", "ok_sec.pdf"),
        ]
        raw_email = _build_email(
            from_addr="sales@acme.com",
            message_id="<sec-fail@acme.com>",
            attachments=email_attachments,
        )

        result = orchestrator_module.process_inbound_email(
            settings,
            tenant_id=context.workspace.tenant_id,
            raw_email_bytes=raw_email,
            raw_email_ref=None,
        )

        # Primary flow succeeds despite secondary attachment upload failure
        assert result["status"] == "completed"
        # Primary and succeeding secondary uploaded (2 out of 3)
        assert len(uploads) == 2
        uploaded_paths = [u[0] for u in uploads]
        assert any("primary.pdf" in p for p in uploaded_paths)
        assert any("ok_sec.pdf" in p for p in uploaded_paths)
        assert not any("failing_sec.pdf" in p for p in uploaded_paths)

        assert len(enqueued) == 1
        assert str(enqueued[0]["document_id"]) == result["document_id"]
        assert str(enqueued[0]["quotation_id"]) == result["quotation_id"]

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, storage_path from document where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                doc_rows = cur.fetchall()

                cur.execute(
                    "select id, document_id from quotation where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                quotation_rows = cur.fetchall()

                cur.execute(
                    "select id, status from extraction_job where tenant_id = %s",
                    (context.workspace.tenant_id,),
                )
                job_rows = cur.fetchall()

        # 2 documents stored in DB (primary and successful secondary)
        assert len(doc_rows) == 2
        assert len(quotation_rows) == 1
        assert str(quotation_rows[0]["document_id"]) == result["document_id"]
        assert len(job_rows) == 1
        assert job_rows[0]["status"] == "queued"
