from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from procurepilot_api.modules.documents.schemas import Document

# document_source_channel's real Postgres enum has four values (migrations across R3.0/R4.3);
# the Pydantic schema only ever allowed "upload" until this was found via a live walkthrough --
# GET /quotations/{id} 500ed for any document captured through /capture (source_channel=
# 'capture'), and would 500 identically for 'email'/'catalogue_import' too. Every value here must
# stay in sync with the DB enum, not just the ones a given test fixture happens to use.
_ALL_DB_SOURCE_CHANNELS = ("upload", "email", "capture", "catalogue_import")


@pytest.mark.parametrize("source_channel", _ALL_DB_SOURCE_CHANNELS)
def test_document_accepts_every_real_source_channel(source_channel: str) -> None:
    doc = Document.model_validate(
        {
            "id": str(uuid4()),
            "storage_bucket": "quotation-documents",
            "storage_path": "tenants/x/quotations/y/z.pdf",
            "mime_type": "application/pdf",
            "content_hash": None,
            "source_channel": source_channel,
            "status": "uploaded",
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": str(uuid4()),
        }
    )
    assert doc.source_channel == source_channel
