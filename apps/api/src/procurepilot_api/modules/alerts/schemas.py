from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AlertKind = Literal[
    "recommended_price_expiring",
    "preferred_supplier_offer_disappeared",
    "price_swing",
    "price_spike",
    "likely_duplicate_quotation_line",
    "decimal_or_quantity_anomaly",
    "delivery_cost_anomaly",
    "supplier_quality_trend_change",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertAction = Literal[
    "compare_product",
    "review_supplier",
    "view_price_history",
    "inspect_scorecard",
    "review_quotation",
    "view_delivery_issues",
]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Alert(BaseModel):
    id: str
    kind: AlertKind
    workspace_product_id: UUID
    severity: AlertSeverity
    evidence: dict[str, object]
    action: AlertAction
    created_from_current_data_at: datetime
    dismissed: bool
    supplier_id: UUID | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    valid_until: datetime | None = None


class AlertList(BaseModel):
    items: list[Alert]
    next_cursor: str | None = None


class AlertDismissal(BaseModel):
    alert_id: str
    dismissed_at: datetime
