from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from procurepilot_api.modules.alerts.schemas import Alert, AlertDismissal, AlertList


def test_alert_contract_is_actionable_and_dismissal_only() -> None:
    alert = Alert(
        id="price_swing:abc",
        kind="price_swing",
        workspace_product_id=uuid4(),
        supplier_id=uuid4(),
        severity="critical",
        evidence={"swing_percentage": "20.00"},
        action="view_price_history",
        created_from_current_data_at=datetime.now(UTC),
        dismissed=False,
    )
    assert AlertList(items=[alert]).items[0].action == "view_price_history"
    dismissal = AlertDismissal(alert_id=alert.id, dismissed_at=datetime.now(UTC))
    assert dismissal.model_dump(mode="json")["alert_id"] == alert.id
