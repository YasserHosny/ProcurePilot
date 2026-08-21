from __future__ import annotations

import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.exports.schemas import ExportCreate
from procurepilot_api.modules.savings.schemas import PurchaseOutcomeCreate


def test_value_proof_requests_do_not_accept_tenant_id() -> None:
    with pytest.raises(ValidationError):
        PurchaseOutcomeCreate.model_validate(
            {
                "tenant_id": str(uuid4()),
                "workspace_product_id": str(uuid4()),
                "quantity": "1.000000",
                "base_unit": "litre",
                "unit_price": {"amount": "1.0000", "currency": "GBP"},
                "total_paid": {"amount": "1.0000", "currency": "GBP"},
                "delivery_result": "delivered",
            }
        )
    with pytest.raises(ValidationError):
        ExportCreate.model_validate(
            {
                "tenant_id": str(uuid4()),
                "kind": "savings_ledger",
                "format": "xlsx",
                "filters": {"period_start": "2026-08-01", "period_end": "2026-08-31"},
            }
        )


def test_no_real_billing_provider_is_imported_or_called() -> None:
    assert "stripe" not in sys.modules


def test_export_result_reference_is_tenant_checked_through_job_read_not_request_input() -> None:
    fields = set(ExportCreate.model_fields)
    assert "tenant_id" not in fields
    assert "download_url" not in fields
