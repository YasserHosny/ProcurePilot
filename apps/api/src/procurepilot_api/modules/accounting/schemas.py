"""Pydantic request and response schemas for accounting integration (R3.1).

Defines AccountingConnection, StartConnectionResponse, SyncedBill, SyncedBillList,
and TriggerSyncResponse per OpenAPI contract.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class TriggerSyncResponse(BaseModel):
    """Response returned when an on-demand accounting sync is triggered (T022)."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["enqueued"] = "enqueued"


class SyncedBill(BaseModel):
    """A supplier bill synced from the external accounting provider (T014-continuation, US2).

    Field-for-field matches contracts/accounting-integration.openapi.yaml
    components/schemas/SyncedBill.
    Amount is serialized to string (never a float) to maintain precision.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_name: str
    matched_supplier_id: UUID | None = None
    amount: str
    currency: str
    bill_date: date
    provider_status: Literal["open", "paid", "void"]
    matched: bool
    purchase_record_id: UUID | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount_to_str(cls, value: object) -> str:
        if isinstance(value, Decimal):
            return str(value)
        return str(value)


class SyncedBillList(BaseModel):
    """Cursor-paginated list of synced bills (T014-continuation, US2)."""

    model_config = ConfigDict(from_attributes=True)

    items: list[SyncedBill]
    next_cursor: str | None = None


class SyncedBillDetail(BaseModel):
    """Denormalized detail for a linked synced bill (R3.1, US3, decision #1)."""

    model_config = ConfigDict(from_attributes=True)

    vendor_name: str
    amount: str
    currency: str
    bill_date: date

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount_to_str(cls, value: object) -> str:
        if isinstance(value, Decimal):
            return str(value)
        return str(value)


class PurchaseRecordDetail(BaseModel):
    """Denormalized detail for a linked purchase record (R3.1, US3, decision #1)."""

    model_config = ConfigDict(from_attributes=True)

    supplier_name: str | None = None
    amount: str
    currency: str
    date: date

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount_to_str(cls, value: object) -> str:
        if isinstance(value, Decimal):
            return str(value)
        return str(value)


class ReconciliationDiscrepancy(BaseModel):
    """A flagged reconciliation exception (T029, US3).

    Field-for-field matches contracts/accounting-integration.openapi.yaml
    components/schemas/ReconciliationDiscrepancy, extended with read-only nested
    synced_bill_detail and purchase_record_detail objects (decision #1).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    discrepancy_type: Literal["amount_mismatch", "unmatched_bill", "unmatched_purchase"]
    synced_bill_id: UUID | None = None
    purchase_record_id: UUID | None = None
    status: Literal["open", "resolved"]
    detected_at: datetime
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None

    synced_bill_detail: SyncedBillDetail | None = None
    purchase_record_detail: PurchaseRecordDetail | None = None


class ReconciliationDiscrepancyList(BaseModel):
    """Cursor-paginated list of reconciliation discrepancies (T029, US3)."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ReconciliationDiscrepancy]
    next_cursor: str | None = None


class ResolveDiscrepancyRequest(BaseModel):
    """Optional request body for resolving a reconciliation discrepancy (T029, US3)."""

    model_config = ConfigDict(from_attributes=True)

    note: str | None = Field(default=None, max_length=2000)


__all__ = [
    "AccountingConnection",
    "PurchaseRecordDetail",
    "ReconciliationDiscrepancy",
    "ReconciliationDiscrepancyList",
    "ResolveDiscrepancyRequest",
    "StartConnectionResponse",
    "SyncedBill",
    "SyncedBillDetail",
    "SyncedBillList",
    "TriggerSyncResponse",
]
