from __future__ import annotations

import hashlib
from uuid import UUID


def alert_fingerprint(
    *,
    tenant_id: UUID,
    kind: str,
    product_id: UUID,
    supplier_id: UUID | None,
    recurrence_key: str,
) -> str:
    parts = [
        str(tenant_id),
        kind,
        str(product_id),
        "" if supplier_id is None else str(supplier_id),
        recurrence_key,
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


def price_spike_recurrence_key(landed_cost_id: UUID, spike_percentage: str) -> str:
    return f"{landed_cost_id}:{spike_percentage}"


def duplicate_line_recurrence_key(line_id_1: UUID, line_id_2: UUID) -> str:
    first = min(str(line_id_1), str(line_id_2))
    second = max(str(line_id_1), str(line_id_2))
    return f"{first}:{second}"


def decimal_anomaly_recurrence_key(landed_cost_id: UUID, ratio: str) -> str:
    return f"{landed_cost_id}:{ratio}"


def delivery_cost_recurrence_key(supplier_id: UUID, delivery_fee_amount: str) -> str:
    return f"{supplier_id}:{delivery_fee_amount}"


def supplier_quality_recurrence_key(
    supplier_id: UUID,
    dispute_rate: str,
    quality_score: str,
    incident_count: int,
) -> str:
    return f"{supplier_id}:{dispute_rate}:{quality_score}:{incident_count}"
