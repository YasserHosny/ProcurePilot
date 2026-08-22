from __future__ import annotations

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
                filename="supplier-quote.pdf",
                mime_type="application/pdf",
                size_bytes=128,
                content_hash="abc123",
            ),
        )

        assert response.storage_bucket == "quotation-documents"
        assert response.storage_path.startswith(f"tenants/{workspace.tenant_id}/quotations/")
        cur.execute(
            "select mime_type, content_hash, created_by from document where id = %s",
            (response.document_id,),
        )
        assert cur.fetchone() == ("application/pdf", "abc123", workspace.membership_id)


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
