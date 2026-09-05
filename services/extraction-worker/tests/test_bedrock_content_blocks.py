from __future__ import annotations

from unittest.mock import MagicMock, patch

from procurepilot_extraction_worker.bedrock import BedrockExtractionProvider
from procurepilot_extraction_worker.settings import WorkerSettings


def _settings() -> WorkerSettings:
    return WorkerSettings(
        database_url="postgresql://localhost/test",
        supabase_url="http://localhost",
        supabase_service_role_key="test",
    )


def _converse_response() -> dict[str, object]:
    return {
        "output": {"message": {"content": [{"text": '{"header": {}, "lines": []}'}]}},
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def _content_blocks(mime_type: str) -> list[dict[str, object]]:
    mock_client = MagicMock()
    mock_client.converse.return_value = _converse_response()
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client

    with patch(
        "procurepilot_extraction_worker.bedrock.boto3.Session",
        return_value=mock_session,
    ):
        provider = BedrockExtractionProvider(settings=_settings())
        provider.extract(
            document_id="doc-1",
            mime_type=mime_type,
            storage_path="path",
            document_bytes=b"fake",
        )

    messages = mock_client.converse.call_args.kwargs["messages"]
    return messages[0]["content"]


def test_png_uses_image_content_block() -> None:
    content = _content_blocks("image/png")
    assert any("image" in block for block in content)
    assert not any("document" in block for block in content)
    image_block = next(block for block in content if "image" in block)
    assert image_block["image"]["format"] == "png"


def test_pdf_uses_document_content_block() -> None:
    content = _content_blocks("application/pdf")
    assert any("document" in block for block in content)
    assert not any("image" in block for block in content)
    document_block = next(block for block in content if "document" in block)
    assert document_block["document"]["format"] == "pdf"
