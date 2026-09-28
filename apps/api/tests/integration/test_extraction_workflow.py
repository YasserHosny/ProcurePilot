from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_quotation,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.extraction import service as extraction_service_module
from procurepilot_api.modules.extraction.service import ExtractionService
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.service import QuotationService

WORKER_SRC = Path(__file__).resolve().parents[4] / "services" / "extraction-worker" / "src"
sys.path.insert(0, str(WORKER_SRC))

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for extraction workflow integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_structured_extraction_writes_lines_fields_and_review_task(conn: object) -> None:
    from procurepilot_extraction_worker.structured_parse import parse_structured_content
    from procurepilot_extraction_worker.validation import validate_arithmetic
    from procurepilot_extraction_worker.worker import (
        SupplierMatch,
        _persist_result,
        _update_quotation_status,
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

        _persist_result(conn, workspace.tenant_id, quotation_id, result, arithmetic.status)
        _update_quotation_status(
            conn,
            quotation_id,
            "in_review",
            arithmetic.status,
            result,
            SupplierMatch(None, None, had_candidates=False),
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
