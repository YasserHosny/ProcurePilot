from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as, connection, make_workspace
from integration.quotation_helpers import PsycopgSupabaseClient
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnsupportedMediaTypeError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.documents import service as document_service_module
from procurepilot_api.modules.documents.schemas import PresignRequest
from procurepilot_api.modules.documents.service import DocumentService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for quotation upload integration tests",
)


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_presigned_upload_metadata_creation_for_accepted_mime(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-upload")
        act_as(cur, workspace)
        monkeypatch.setattr(
            document_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        response = DocumentService().create_presigned_upload(
            bearer_token="test-token",
            member=member,
            payload=PresignRequest(
                filename="عرض-سعر-الأمانة.pdf",
                mime_type="application/pdf",
                size_bytes=128,
                content_hash="abc123",
            ),
        )

        assert response.storage_bucket == "quotation-documents"
        assert response.storage_path.startswith(f"tenants/{workspace.tenant_id}/quotations/")
        assert response.storage_path.isascii()
        cur.execute(
            "select mime_type, content_hash, created_by, original_filename "
            "from document where id = %s",
            (response.document_id,),
        )
        assert cur.fetchone() == (
            "application/pdf",
            "abc123",
            workspace.membership_id,
            "عرض-سعر-الأمانة.pdf",
        )
        document = DocumentService().get_document(
            bearer_token="test-token", document_id=response.document_id
        )
        assert document.original_filename == "عرض-سعر-الأمانة.pdf"


def test_presigned_upload_refuses_unsupported_mime_before_writing(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-upload-refused")
        act_as(cur, workspace)
        monkeypatch.setattr(
            document_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )
        payload = PresignRequest.model_construct(
            filename="quote.exe",
            mime_type="application/x-msdownload",
            size_bytes=128,
            content_hash=None,
        )

        with pytest.raises(UnsupportedMediaTypeError):
            DocumentService().create_presigned_upload(
                bearer_token="test-token",
                member=member,
                payload=payload,
            )

        cur.execute("select count(*) from document where tenant_id = %s", (workspace.tenant_id,))
        assert cur.fetchone() == (0,)


def test_document_download_disposition_preserves_inline_preview_and_unicode_filename(
    conn: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Bucket:
        def create_signed_url(self, _path: str, *, expires_in: int) -> dict[str, str]:
            assert expires_in == 300
            return {"signedURL": "https://storage.example.test/signed?token=abc%2B123%3D%3D"}

    class _Storage:
        def from_(self, _bucket: str) -> _Bucket:
            return _Bucket()

    class _StorageClient:
        storage = _Storage()

    with conn.cursor() as cur:
        workspace = make_workspace(cur, "quotation-download-disposition")
        act_as(cur, workspace)
        monkeypatch.setattr(
            document_service_module,
            "authenticated_client",
            lambda _settings, _token: PsycopgSupabaseClient(conn),
        )
        monkeypatch.setattr(
            document_service_module, "create_client", lambda *_args: _StorageClient()
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )
        document = DocumentService().create_presigned_upload(
            bearer_token="test-token",
            member=member,
            payload=PresignRequest(
                filename="عرض-سعر-النور.pdf",
                mime_type="application/pdf",
                size_bytes=128,
            ),
        )
        service = DocumentService()

        inline = service.create_download_url(
            bearer_token="test-token", document_id=document.document_id
        )
        attachment = service.create_download_url(
            bearer_token="test-token",
            document_id=document.document_id,
            disposition="attachment",
        )

    inline_query = parse_qs(urlsplit(inline.download_url).query)
    attachment_query = parse_qs(urlsplit(attachment.download_url).query)
    assert "download" not in inline_query
    assert attachment_query["download"] == ["عرض-سعر-النور.pdf"]
    assert attachment_query["token"] == ["abc+123=="]
