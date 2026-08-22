from __future__ import annotations

from uuid import uuid4

from procurepilot_api.modules.alerts.fingerprints import alert_fingerprint


def test_alert_fingerprint_is_deterministic_and_recurrence_key_sensitive() -> None:
    tenant_id = uuid4()
    product_id = uuid4()
    supplier_id = uuid4()
    first = alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_swing",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key="landed-cost-a:15.00",
    )
    assert first == alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_swing",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key="landed-cost-a:15.00",
    )
    assert first != alert_fingerprint(
        tenant_id=tenant_id,
        kind="price_swing",
        product_id=product_id,
        supplier_id=supplier_id,
        recurrence_key="landed-cost-b:15.00",
    )
