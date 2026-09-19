"""Pydantic request and response schemas for POS and inventory integration (R3.2).

Defines PosConnection, StartConnectionResponse, TriggerSyncResponse,
ManualMatchRequest, SyncedProductSignal, SyncedProductSignalList,
and PosProductMatch per contracts/pos-integration.openapi.yaml.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class StartConnectionResponse(BaseModel):
    """Response returned when starting the Square OAuth connection flow (T012)."""

    model_config = ConfigDict(from_attributes=True)

    authorization_url: str


class PosConnection(BaseModel):
    """An external POS/inventory system connection for a tenant (T012).

    Field-for-field matches contracts/pos-integration.openapi.yaml
    components/schemas/PosConnection.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: Literal["square"]
    display_name: str
    status: Literal["active", "needs_reauth", "disconnected"]
    connected_at: datetime
    last_synced_at: datetime | None = None
    disconnected_at: datetime | None = None


class TriggerSyncResponse(BaseModel):
    """Response returned when an on-demand POS sync is triggered (T020)."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["enqueued"] = "enqueued"


class ManualMatchRequest(BaseModel):
    """Request payload to manually link an unmatched signal to a workspace product (T021)."""

    model_config = ConfigDict(from_attributes=True)

    workspace_product_id: UUID


class SyncedProductSignal(BaseModel):
    """A sales-velocity and/or stock-on-hand signal for an external item (T020).

    Field-for-field matches contracts/pos-integration.openapi.yaml
    components/schemas/SyncedProductSignal.
    Quantities are serialized to strings (never floats) to preserve precision.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_item_name: str
    matched: bool
    matched_workspace_product_id: UUID | None = None
    stock_on_hand: str | None = None
    stock_synced_at: datetime | None = None
    sales_velocity_per_day: str | None = None
    velocity_window_days: int
    velocity_window_days_observed: int | None = None
    velocity_computed_at: datetime | None = None

    @field_validator("stock_on_hand", "sales_velocity_per_day", mode="before")
    @classmethod
    def _coerce_decimal_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, (Decimal, float, int)):
            return str(v)
        return str(v)


class SyncedProductSignalList(BaseModel):
    """Cursor-paginated list of synced product signals (T020)."""

    model_config = ConfigDict(from_attributes=True)

    items: list[SyncedProductSignal]
    next_cursor: str | None = None


class PosProductMatch(BaseModel):
    """The link between a synced product signal and a workspace product (T021)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    synced_product_signal_id: UUID
    workspace_product_id: UUID
    match_method: Literal["automatic", "manual"]
    matched_at: datetime
