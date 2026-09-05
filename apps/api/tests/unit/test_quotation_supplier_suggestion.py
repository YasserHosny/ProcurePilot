from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter

from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.schemas import ReviewTaskReason
from procurepilot_api.modules.quotations.service import QuotationService


def test_review_task_reason_accepts_no_supplier_match() -> None:
    assert TypeAdapter(ReviewTaskReason).validate_python("no_supplier_match") == "no_supplier_match"


def test_get_quotation_returns_suggested_supplier_name(monkeypatch: pytest.MonkeyPatch) -> None:
    quotation_id = uuid4()
    document_id = uuid4()
    uploader_id = uuid4()
    supplier_id = uuid4()
    now = datetime.now(UTC)

    quote_row = {
        "id": quotation_id,
        "document_id": document_id,
        "supplier_id": None,
        "suggested_supplier_id": supplier_id,
        "supplier_match_confidence": "0.735",
        "currency": "GBP",
        "issue_date": None,
        "expiry_date": None,
        "status": "in_review",
        "previous_quotation_id": None,
        "stated_total_amount": None,
        "stated_total_currency": None,
        "arithmetic_status": "reconciled",
        "created_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
        "deleted_at": None,
        "reviewer_notes": None,
    }
    document_row = {
        "id": document_id,
        "storage_bucket": "quotation-documents",
        "storage_path": "tenants/test/quote.pdf",
        "mime_type": "application/pdf",
        "content_hash": "hash",
        "source_channel": "upload",
        "status": "uploaded",
        "created_at": now,
        "created_by": uploader_id,
    }

    monkeypatch.setattr(
        quotation_service_module,
        "authenticated_client",
        lambda _settings, _token: object(),
    )
    monkeypatch.setattr(quotation_service_module, "_quotation_row", lambda _client, _id: quote_row)
    monkeypatch.setattr(
        quotation_service_module,
        "_document_row",
        lambda _client, _id: document_row,
    )
    monkeypatch.setattr(quotation_service_module, "_line_rows", lambda _client, _id: [])
    monkeypatch.setattr(quotation_service_module, "_field_rows", lambda _client, _id: [])
    monkeypatch.setattr(quotation_service_module, "_open_or_latest_task", lambda _client, _id: None)
    monkeypatch.setattr(quotation_service_module, "_next_versions", lambda _client, _id: [])
    monkeypatch.setattr(quotation_service_module, "_membership_email", lambda _client, _id: None)

    seen_supplier_ids: list[UUID] = []

    def supplier_name(_client: object, resolved_supplier_id: UUID) -> str:
        seen_supplier_ids.append(resolved_supplier_id)
        return "Fresh Farms Ltd"

    monkeypatch.setattr(quotation_service_module, "_supplier_name", supplier_name)

    detail = QuotationService().get_quotation(
        bearer_token="test-token",
        quotation_id=quotation_id,
    )

    assert detail.suggested_supplier_id == supplier_id
    assert detail.supplier_match_confidence == "0.735"
    assert detail.suggested_supplier_name == "Fresh Farms Ltd"
    assert seen_supplier_ids == [supplier_id]
