from __future__ import annotations

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import committed_smart_context, settings_for_test_db
from procurepilot_api.modules.ingestion import capture_service as capture_service_module
from procurepilot_api.modules.ingestion.capture_service import CaptureService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)

class _FakeAuditWriter:
    def record(self, *args: object, **kwargs: object) -> None:
        pass


@pytest.fixture(autouse=True)
def _mock_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture_service_module, "get_audit_writer", lambda: _FakeAuditWriter())

# A minimal real PDF header — enough for libmagic to detect application/pdf, one of
# CaptureService's accepted mime types.
_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


class _FakeBucket:
    def upload(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeStorage:
    def from_(self, _bucket: str) -> _FakeBucket:
        return _FakeBucket()


class _FakeSupabaseClient:
    storage = _FakeStorage()


@pytest.fixture(autouse=True)
def _fake_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        capture_service_module, "create_client", lambda *_a, **_k: _FakeSupabaseClient()
    )


@pytest.fixture
def _fake_queue(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    enqueued: list[dict[str, object]] = []
    monkeypatch.setattr(
        capture_service_module,
        "enqueue_extraction",
        lambda settings, **kwargs: enqueued.append(kwargs),
    )
    return enqueued


def test_capture_creates_pending_quotation_and_queues_extraction(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-basic", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        service = CaptureService(settings)

        result = service.create_capture(
            member=context.member,
            file_content=_PDF_BYTES,
            filename="delivery-note.pdf",
            supplier_id=supplier_id,
            notes="left at reception",
            bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
        )

        assert result["status"] == "pending"
        quotation_id = result["quotation_id"]

        assert len(_fake_queue) == 1
        assert _fake_queue[0]["quotation_id"] == quotation_id

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, source, supplier_id, document_id from quotation where id = %s",
                    (quotation_id,),
                )
                quotation = cur.fetchone()
                assert quotation is not None
                assert quotation["status"] == "pending"
                assert quotation["source"] == "capture"
                assert quotation["supplier_id"] == supplier_id

                cur.execute(
                    "select mime_type, source_channel, status from document where id = %s",
                    (quotation["document_id"],),
                )
                document = cur.fetchone()
                assert document is not None
                assert document["mime_type"] == "application/pdf"
                assert document["source_channel"] == "capture"

                cur.execute(
                    "select status from extraction_job where quotation_id = %s",
                    (quotation_id,),
                )
                job = cur.fetchone()
                assert job is not None
                assert job["status"] == "queued"


def test_capture_creates_pending_quotation_for_an_image_upload(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-image", supplier_count=1) as context:
        supplier_id = context.supplier_ids[0]
        service = CaptureService(settings)

        result = service.create_capture(
            member=context.member,
            file_content=_JPEG_BYTES,
            filename="delivery-photo.jpg",
            supplier_id=supplier_id,
            notes="left at reception",
            bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
        )

        assert result["status"] == "pending"
        quotation_id = result["quotation_id"]

        assert len(_fake_queue) == 1
        assert _fake_queue[0]["quotation_id"] == quotation_id

        with psycopg.connect(TEST_DATABASE_URL or "", row_factory=psycopg.rows.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select status, source, supplier_id, document_id from quotation where id = %s",
                    (quotation_id,),
                )
                quotation = cur.fetchone()
                assert quotation is not None
                assert quotation["status"] == "pending"
                assert quotation["source"] == "capture"
                assert quotation["supplier_id"] == supplier_id

                cur.execute(
                    "select mime_type, source_channel, status from document where id = %s",
                    (quotation["document_id"],),
                )
                document = cur.fetchone()
                assert document is not None
                assert document["mime_type"] == "image/jpeg"
                assert document["source_channel"] == "capture"

                cur.execute(
                    "select status from extraction_job where quotation_id = %s",
                    (quotation_id,),
                )
                job = cur.fetchone()
                assert job is not None
                assert job["status"] == "queued"


def test_capture_without_supplier_id_is_allowed(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-no-supplier", supplier_count=1) as context:
        service = CaptureService(settings)

        result = service.create_capture(
            member=context.member,
            file_content=_PDF_BYTES,
            filename="receipt.pdf",
            supplier_id=None,
            notes=None,
            bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
        )

        assert result["status"] == "pending"
        assert len(_fake_queue) == 1


def test_capture_rejects_oversized_file(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    monkeypatch.setenv("CAPTURE_MAX_BYTES", "100")
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-oversized", supplier_count=1) as context:
        service = CaptureService(settings)

        with pytest.raises(Exception):  # noqa: B017 - UnprocessableEntityError
            service.create_capture(
                member=context.member,
                file_content=_PDF_BYTES * 20,
                filename="huge.pdf",
                supplier_id=None,
                notes=None,
                bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
            )

        assert _fake_queue == []


def test_capture_rejects_unsupported_mime_type(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-badmime", supplier_count=1) as context:
        service = CaptureService(settings)

        with pytest.raises(Exception):  # noqa: B017 - UnsupportedMediaTypeError
            service.create_capture(
                member=context.member,
                file_content=b"this is plain text, not an accepted capture format",
                filename="notes.txt",
                supplier_id=None,
                notes=None,
                bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
            )

        assert _fake_queue == []


def test_capture_unknown_supplier_id_not_found(
    monkeypatch: pytest.MonkeyPatch, _fake_queue: list[dict[str, object]]
) -> None:
    from uuid import uuid4

    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("capture-badsupplier", supplier_count=1) as context:
        service = CaptureService(settings)

        with pytest.raises(Exception):  # noqa: B017 - NotFoundError
            service.create_capture(
                member=context.member,
                file_content=_PDF_BYTES,
                filename="delivery-note.pdf",
                supplier_id=uuid4(),
                notes=None,
                bearer_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature",
            )

        assert _fake_queue == []
