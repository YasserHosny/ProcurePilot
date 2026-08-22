from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AlertKind = Literal[
    "recommended_price_expiring",
    "preferred_supplier_offer_disappeared",
    "price_swing",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertAction = Literal["compare_product", "review_supplier", "view_price_history"]


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


class AlertList(BaseModel):
    items: list[Alert]
    next_cursor: str | None = None


class AlertDismissal(BaseModel):
    alert_id: str
    dismissed_at: datetime
