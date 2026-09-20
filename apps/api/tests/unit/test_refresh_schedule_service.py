from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.offers.refresh_schedule_service import _schedule_from_row


def test_schedule_response_ignores_database_tenant_column() -> None:
    product_id = uuid4()
    supplier_id = uuid4()
    now = datetime.now(UTC)

    schedule = _schedule_from_row(
        {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "workspace_product_id": product_id,
            "supplier_id": supplier_id,
            "cadence_days": 14,
            "status": "active",
            "next_refresh_at": now,
            "last_observed_at": None,
            "last_requested_at": None,
            "last_error": None,
            "source_import_id": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert schedule.workspace_product_id == product_id
    assert schedule.supplier_id == supplier_id
