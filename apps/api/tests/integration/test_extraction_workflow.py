from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_quotation,
    make_supplier,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, ServiceUnavailableError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.extraction import service as extraction_service_module
from procurepilot_api.modules.extraction.service import ExtractionService
from procurepilot_api.modules.quotations import review_service as review_service_module
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.review_service import QuotationReviewService
from procurepilot_api.modules.quotations.schemas import FieldCorrection, QuotationReviewPatch
from procurepilot_api.modules.quotations.service import QuotationService
from procurepilot_api.shared.audit import AuditEventCreate

WORKER_SRC = Path(__file__).resolve().parents[4] / "services" / "extraction-worker" / "src"
sys.path.insert(0, str(WORKER_SRC))

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for extraction workflow integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


class _NoopAuditWriter:
    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del event, bearer_token


def test_structured_extraction_writes_lines_fields_and_review_task(conn: object) -> None:
    from procurepilot_extraction_worker.structured_parse import parse_structured_content
    from procurepilot_extraction_worker.validation import validate_arithmetic
    from procurepilot_extraction_worker.worker import (
        SupplierMatch,
        _persist_result,
        _update_quotation_status,
        _with_normalised_dates,
    )

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "structured-extraction")
        ensure_quotation_reference_data(cur)
        document_id = make_document(cur, workspace, mime_type="text/csv", filename="quote.csv")
        quotation_id = make_quotation(cur, workspace, document_id=document_id, status="extracting")
        content = (
            b"supplier_name,currency,description,quantity,unit_price,stated_total\n"
            b"Acme,GBP,Tomatoes,2,10.00,25.00\n"
        )
        result = parse_structured_content(content, mime_type="text/csv")
        arithmetic = validate_arithmetic(result)
        result, parsed_dates, _ = _with_normalised_dates(result, None)

        _persist_result(conn, workspace.tenant_id, quotation_id, result, arithmetic.status)
        _update_quotation_status(
            conn,
            quotation_id,
            "in_review",
            arithmetic.status,
            result,
            SupplierMatch(None, None, had_candidates=False),
            parsed_dates,
        )

        act_as(cur, workspace)
        cur.execute("select count(*) from quotation_line where quotation_id = %s", (quotation_id,))
        assert cur.fetchone() == (1,)
        cur.execute(
            "select field_name, confidence, extraction_method from field_extraction "
            "where quotation_id = %s order by field_name",
            (quotation_id,),
        )
        fields = cur.fetchall()
        assert ("currency", 1, "structured_parse") in fields
        assert ("unit_price", 1, "structured_parse") in fields
        cur.execute(
            "select status, priority, reason from review_task where quotation_id = %s",
            (quotation_id,),
        )
        assert cur.fetchone() == ("open", "high", "arithmetic_mismatch")


def test_extraction_parses_egyptian_date_and_routes_bad_expiry_to_review(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import procurepilot_extraction_worker.worker as extraction_worker
    from procurepilot_extraction_worker.models import ExtractedField, ExtractionResult
    from procurepilot_extraction_worker.settings import WorkerSettings
    from procurepilot_extraction_worker.worker import process_extraction_job

    @contextmanager
    def mdy_connection(dsn: str) -> object:
        import psycopg

        with psycopg.connect(dsn, prepare_threshold=None) as extraction_conn:
            extraction_conn.execute("set datestyle to 'ISO, MDY'")
            yield extraction_conn

    monkeypatch.setattr(extraction_worker.db, "connect", mdy_connection)

    with conn.cursor() as cur:
        workspace = make_workspace(cur, f"extraction-date-eg-{uuid4().hex[:8]}")
        cur.execute(
            "insert into supported_region (code,label_en,label_ar) values ('EG','Egypt','مصر') "
            "on conflict do nothing"
        )
        cur.execute(
            "insert into supported_currency (code,label_en,label_ar) "
            "values ('EGP','Egyptian Pound','جنيه مصري') on conflict do nothing"
        )
        cur.execute(
            "update tenant set region='EG', currency='EGP' where id=%s", (workspace.tenant_id,)
        )
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(cur, workspace, document_id=document_id, status="extracting")
        job_id = uuid4()
        cur.execute(
            "insert into extraction_job (id,tenant_id,quotation_id,status) "
            "values (%s,%s,%s,'queued')",
            (job_id, workspace.tenant_id, quotation_id),
        )
        conn.commit()

    result = ExtractionResult(
        method="bedrock",
        model_version="date-test",
        header={
            "currency": ExtractedField("currency", "EGP", 0.99),
            "issue_date": ExtractedField("issue_date", "16/10/2026", 0.99),
            "expiry_date": ExtractedField("expiry_date", "soon", 0.99),
        },
        lines=[],
    )
    monkeypatch.setattr(
        "procurepilot_extraction_worker.worker.get_settings",
        lambda: WorkerSettings(
            database_url=TEST_DATABASE_URL or "", supabase_url="", supabase_service_role_key=""
        ),
    )
    monkeypatch.setattr(
        "procurepilot_extraction_worker.worker._extract", lambda *_args, **_kwargs: result
    )
    process_extraction_job(
        {
            "job_id": str(job_id),
            "tenant_id": str(workspace.tenant_id),
            "quotation_id": str(quotation_id),
            "document_id": str(document_id),
        }
    )
    with conn.cursor() as cur:
        act_as(cur, workspace)
        cur.execute(
            "select status, issue_date, expiry_date from quotation where id=%s", (quotation_id,)
        )
        assert cur.fetchone() == ("in_review", date(2026, 10, 16), None)
        cur.execute(
            "select extracted_value from field_extraction "
            "where quotation_id=%s and field_name='issue_date'",
            (quotation_id,),
        )
        assert cur.fetchone() == ("16/10/2026",)
        cur.execute("select status from extraction_job where id=%s", (job_id,))
        assert cur.fetchone() == ("succeeded",)
        cur.execute("select reason from review_task where quotation_id=%s", (quotation_id,))
        assert cur.fetchone() == ("date_unparsed",)
        cur.execute(
            "select id from field_extraction where quotation_id=%s and field_name='expiry_date'",
            (quotation_id,),
        )
        expiry_field_id = cur.fetchone()[0]
        cur.execute(
            "select confidence,extracted_value from field_extraction where id=%s",
            (expiry_field_id,),
        )
        assert cur.fetchone() == (0, "soon")
        supplier_id = make_supplier(cur, workspace, "Review Date Supplier")
        conn.commit()
        monkeypatch.setattr(
            review_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            review_service_module, "get_audit_writer", lambda: _NoopAuditWriter()
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )
        review_service = QuotationReviewService()
        review_service.apply_review_patch(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
            patch=QuotationReviewPatch(supplier_id=supplier_id),
        )
        with conn.cursor() as verify_cur:
            act_as(verify_cur, workspace)
            verify_cur.execute(
                "select reason,status from review_task where quotation_id=%s", (quotation_id,)
            )
            assert verify_cur.fetchone() == ("date_unparsed", "open")
        with pytest.raises(ConflictError):
            review_service.apply_review_patch(
                bearer_token="test-token",
                member=member,
                quotation_id=quotation_id,
                patch=QuotationReviewPatch(
                    corrections=[
                        FieldCorrection(
                            field_extraction_id=expiry_field_id, corrected_value="soon"
                        )
                    ]
                ),
            )
        review_service.apply_review_patch(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
            patch=QuotationReviewPatch(
                corrections=[
                    FieldCorrection(
                        field_extraction_id=expiry_field_id, corrected_value="2026-10-20"
                    )
                ]
            ),
        )
        with conn.cursor() as verify_cur:
            act_as(verify_cur, workspace)
            verify_cur.execute("select expiry_date from quotation where id=%s", (quotation_id,))
            assert verify_cur.fetchone() == (date(2026, 10, 20),)
            verify_cur.execute(
                "select reason,status from review_task where quotation_id=%s", (quotation_id,)
            )
            assert verify_cur.fetchone() == ("date_unparsed", "resolved")

        ambiguous_document_id = make_document(cur, workspace)
        ambiguous_quotation_id = make_quotation(
            cur, workspace, document_id=ambiguous_document_id, status="extracting"
        )
        ambiguous_job_id = uuid4()
        cur.execute(
            "insert into extraction_job (id,tenant_id,quotation_id,status) "
            "values (%s,%s,%s,'queued')",
            (ambiguous_job_id, workspace.tenant_id, ambiguous_quotation_id),
        )
        conn.commit()

    ambiguous_result = ExtractionResult(
        method="bedrock",
        model_version="date-test",
        header={
            "currency": ExtractedField("currency", "EGP", 0.99),
            "issue_date": ExtractedField("issue_date", "05/10/2026", 0.99),
        },
        lines=[],
    )
    monkeypatch.setattr(
        "procurepilot_extraction_worker.worker._extract",
        lambda *_args, **_kwargs: ambiguous_result,
    )
    process_extraction_job(
        {
            "job_id": str(ambiguous_job_id),
            "tenant_id": str(workspace.tenant_id),
            "quotation_id": str(ambiguous_quotation_id),
            "document_id": str(ambiguous_document_id),
        }
    )
    with conn.cursor() as cur:
        act_as(cur, workspace)
        cur.execute(
            "select status, issue_date from quotation where id=%s", (ambiguous_quotation_id,)
        )
        assert cur.fetchone() == ("in_review", date(2026, 10, 5))
        cur.execute(
            "select extracted_value from field_extraction "
            "where quotation_id=%s and field_name='issue_date'",
            (ambiguous_quotation_id,),
        )
        assert cur.fetchone() == ("05/10/2026",)
        cur.execute(
            "select reason from review_task where quotation_id=%s", (ambiguous_quotation_id,)
        )
        assert cur.fetchone() == ("low_confidence",)
    from integration.smart_compare_helpers import cleanup_workspace

    cleanup_workspace(workspace)


def test_redis_enqueue_failure_does_not_leave_quotation_stuck(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "redis-failure")
        document_id = make_document(cur, workspace)
        quotation_id = make_quotation(cur, workspace, document_id=document_id)
        act_as(cur, workspace)
        monkeypatch.setattr(
            extraction_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            extraction_service_module,
            "_enqueue_redis_job",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ServiceUnavailableError(details={"dependency": "redis"})
            ),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        with pytest.raises(ServiceUnavailableError):
            ExtractionService().enqueue_extraction(
                bearer_token="test-token",
                member=member,
                quotation_id=quotation_id,
            )

        cur.execute("select status from quotation where id = %s", (quotation_id,))
        assert cur.fetchone() == ("pending",)
        cur.execute(
            "select status, error->>'code' from extraction_job where quotation_id = %s",
            (quotation_id,),
        )
        assert cur.fetchone() == ("failed", "redis_enqueue_failed")

        monkeypatch.setattr(extraction_service_module, "_enqueue_redis_job", lambda *_args: None)
        job, created = ExtractionService().enqueue_extraction(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
        )
        assert created is True
        assert job.status == "queued"


def test_retry_extraction_enqueue_failure_fails_job_without_discarding_review_data(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integration.quotation_helpers import make_extracted_quotation

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "retry-enqueue-failure")
        fixture = make_extracted_quotation(cur, workspace)
        act_as(cur, workspace)
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
            "get_audit_writer",
            lambda: type("AuditWriter", (), {"record": lambda *_args, **_kwargs: None})(),
        )
        monkeypatch.setattr(
            quotation_service_module,
            "_enqueue_extraction",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ServiceUnavailableError(details={"dependency": "redis"})
            ),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        with pytest.raises(ServiceUnavailableError):
            QuotationService().retry_extraction(
                bearer_token="test-token",
                member=member,
                quotation_id=fixture.quotation_id,
            )

        cur.execute("select status from quotation where id = %s", (fixture.quotation_id,))
        assert cur.fetchone() == ("extracted",)
        cur.execute(
            "select status, error->>'code' from extraction_job where quotation_id = %s",
            (fixture.quotation_id,),
        )
        assert cur.fetchone() == ("failed", "redis_enqueue_failed")
        cur.execute(
            "select count(*) from quotation_line where quotation_id = %s",
            (fixture.quotation_id,),
        )
        assert cur.fetchone() == (1,)


def test_replace_document_replays_after_extraction_finished_without_duplicate_job(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integration.quotation_helpers import make_extracted_quotation

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "replace-document-replay")
        fixture = make_extracted_quotation(cur, workspace)
        new_document_id = make_document(cur, workspace, filename="replacement.pdf")
        act_as(cur, workspace)
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
            "get_audit_writer",
            lambda: type("AuditWriter", (), {"record": lambda *_args, **_kwargs: None})(),
        )
        enqueued: list[object] = []
        monkeypatch.setattr(
            quotation_service_module,
            "_enqueue_extraction",
            lambda *_args: enqueued.append(True),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )
        key = uuid4()
        first, first_created = QuotationService().replace_document(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            new_document_id=new_document_id,
            idempotency_key=key,
        )
        cur.execute(
            "update quotation set status = 'extracted' where id = %s",
            (fixture.quotation_id,),
        )
        cur.execute(
            "update extraction_job set status = 'succeeded', completed_at = now() "
            "where quotation_id = %s",
            (fixture.quotation_id,),
        )
        second, second_created = QuotationService().replace_document(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            new_document_id=new_document_id,
            idempotency_key=key,
        )

        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert len(enqueued) == 1
        cur.execute(
            "select count(*) from extraction_job where quotation_id = %s",
            (fixture.quotation_id,),
        )
        assert cur.fetchone() == (1,)


def test_replace_document_retries_failed_enqueue_for_the_same_idempotency_key(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integration.quotation_helpers import make_extracted_quotation

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "replace-document-failed-retry")
        fixture = make_extracted_quotation(cur, workspace)
        new_document_id = make_document(cur, workspace, filename="replacement-retry.pdf")
        act_as(cur, workspace)
        monkeypatch.setattr(
            quotation_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            quotation_service_module,
            "get_audit_writer",
            lambda: type("AuditWriter", (), {"record": lambda *_args, **_kwargs: None})(),
        )
        attempts = 0

        def enqueue(*_args: object, **_kwargs: object) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ServiceUnavailableError(details={"dependency": "redis"})

        monkeypatch.setattr(quotation_service_module, "_enqueue_extraction", enqueue)
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )
        key = uuid4()

        with pytest.raises(ServiceUnavailableError):
            QuotationService().replace_document(
                bearer_token="test-token",
                member=member,
                quotation_id=fixture.quotation_id,
                new_document_id=new_document_id,
                idempotency_key=key,
            )
        retried, created = QuotationService().replace_document(
            bearer_token="test-token",
            member=member,
            quotation_id=fixture.quotation_id,
            new_document_id=new_document_id,
            idempotency_key=key,
        )

        assert created is True
        assert retried.document_id == new_document_id
        assert attempts == 2
        cur.execute(
            "select status from extraction_job where quotation_id = %s and idempotency_key = %s",
            (fixture.quotation_id, key),
        )
        assert cur.fetchone() == ("queued",)
        cur.execute(
            "select count(*) from field_extraction where quotation_id = %s",
            (fixture.quotation_id,),
        )
        assert cur.fetchone() == (1,)
