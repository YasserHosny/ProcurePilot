"""Pydantic request and response schemas for accounting integration (R3.1).

Defines AccountingConnection and StartConnectionResponse per OpenAPI contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StartConnectionResponse(BaseModel):
    """Response returned when starting the QuickBooks OAuth connection flow (T014)."""

    model_config = ConfigDict(from_attributes=True)

    authorization_url: str


class AccountingConnection(BaseModel):
    """An external accounting system connection for a tenant (T014).

    Field-for-field matches contracts/accounting-integration.openapi.yaml
    components/schemas/AccountingConnection.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: Literal["quickbooks"]
    display_name: str
    status: Literal["active", "needs_reauth", "disconnected"]
    connected_at: datetime
    last_synced_at: datetime | None = None
    disconnected_at: datetime | None = None


__all__ = ["AccountingConnection", "StartConnectionResponse"]
