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
