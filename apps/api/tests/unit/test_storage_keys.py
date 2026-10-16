from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

from procurepilot_api.modules.documents.service import _signed_download_url, _storage_path
from procurepilot_api.modules.matching.service import _source_filename
from procurepilot_api.modules.requests.service import _quality_issue_storage_path
from procurepilot_api.shared.storage_keys import (
    content_disposition,
    display_filename,
    safe_object_name,
)


def test_safe_object_names_are_ascii_and_preserve_valid_extensions() -> None:
    examples = [
        "عرض-سعر-النور.pdf",
        "price list.xlsx",
        "quote 😀.pdf",
        "عرض-ABC.pdf",
        "quote.PDF",
        "README",
        ".env",
        "../../x.pdf",
        r"a\b.pdf",
        "a." + "x" * 11,
        "a" * 500 + ".PDF",
    ]
    for name in examples:
        result = safe_object_name(name)
        assert result.isascii()
        assert result and not result.startswith(".") and len(result) <= 100
    assert safe_object_name("عرض-سعر-النور.pdf").endswith(".pdf")
    assert safe_object_name("quote.PDF").endswith(".pdf")
    assert safe_object_name("../../x.pdf") == "x.pdf"
    assert safe_object_name(r"a\b.pdf") == "b.pdf"
    assert not safe_object_name("a." + "x" * 11).endswith("." + "x" * 11)
    assert len(safe_object_name("a" * 500 + ".PDF")) <= 100


def test_display_name_truncates_with_extension_and_normalizes() -> None:
    result = display_filename("nested/عرض-سعر-النور.pdf", fallback="file")
    assert result == "عرض-سعر-النور.pdf"
    long_name = display_filename("a" * 500 + ".pdf", fallback="file")
    assert len(long_name) == 255
    assert long_name.endswith(".pdf")
    assert display_filename("\x00  ", fallback="fallback") == "fallback"


def test_content_disposition_has_rfc5987_unicode_name_and_escaped_ascii_fallback() -> None:
    header = content_disposition('عرض "سعر".pdf')
    encoded = header.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == 'عرض "سعر".pdf'
    assert 'filename="' in header and '\\"' in header


def test_document_and_quality_photo_paths_use_ascii_safe_leaves() -> None:
    tenant_id = UUID("11111111-1111-1111-1111-111111111111")
    document_path = _storage_path(
        tenant_id=tenant_id,
        document_id=UUID("22222222-2222-2222-2222-222222222222"),
        filename="عرض.pdf",
    )
    photo_path = _quality_issue_storage_path(
        tenant_id=tenant_id,
        issue_id=UUID("33333333-3333-3333-3333-333333333333"),
        filename="صورة.png",
    )
    assert document_path.isascii() and document_path.endswith(".pdf")
    assert photo_path.isascii() and photo_path.endswith(".png")


def test_same_named_documents_on_one_entity_get_distinct_storage_paths() -> None:
    tenant_id = UUID("11111111-1111-1111-1111-111111111111")
    first_document_id = UUID("22222222-2222-2222-2222-222222222222")
    second_document_id = UUID("33333333-3333-3333-3333-333333333333")
    first = _storage_path(tenant_id=tenant_id, document_id=first_document_id, filename="quote.pdf")
    second = _storage_path(
        tenant_id=tenant_id, document_id=second_document_id, filename="quote.pdf"
    )

    assert first != second


def test_signed_download_url_encodes_download_name_without_changing_token() -> None:
    signed_url = "https://storage.example/signed?token=abc%2B123%3D%3D"
    original_token = parse_qs(urlsplit(signed_url).query)["token"]
    for filename in ("عرض-سعر-النور.pdf", "a&b #1+2=3.pdf"):
        url = _signed_download_url(signed_url, filename)
        query = parse_qs(urlsplit(url).query)
        assert query["download"] == [filename]
        assert query["token"] == original_token


def test_matching_filename_prefers_original_name_and_falls_back_for_legacy_rows() -> None:
    class _Response:
        def __init__(self, data: list[dict[str, str]]) -> None:
            self.data = data

    class _Query:
        def __init__(self, row: dict[str, str]) -> None:
            self.row = row

        def select(self, _columns: str) -> _Query:
            return self

        def eq(self, _column: str, _value: str) -> _Query:
            return self

        def limit(self, _count: int) -> _Query:
            return self

        def execute(self) -> _Response:
            return _Response([self.row])

    class _Client:
        def __init__(self, row: dict[str, str]) -> None:
            self.row = row

        def table(self, _name: str) -> _Query:
            return _Query(self.row)

    document_id = UUID("22222222-2222-2222-2222-222222222222")
    original = {"storage_path": "tenants/t/quotations/d/file.pdf", "original_filename": "عرض.pdf"}
    legacy = {"storage_path": "tenants/t/quotations/d/file.pdf", "original_filename": None}
    assert _source_filename(_Client(original), document_id) == "عرض.pdf"
    assert _source_filename(_Client(legacy), document_id) == "file.pdf"
