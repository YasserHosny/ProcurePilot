from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

type PurchaseRequestStatus = Literal[
    "draft", "submitted", "approved", "rejected", "withdrawn", "ordered", "delivered"
]
type ApprovalStepStatus = Literal["pending", "approved", "rejected"]
type ApprovalStepSource = Literal["threshold_match", "delegate", "owner_fallback"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class BudgetStatus(BaseModel):
    remaining_amount: Money
    exceeds: bool


class PurchaseRequestLine(BaseModel):
    id: UUID
    workspace_product_id: UUID
    quantity: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")
    quantity_received: StrictStr | None = Field(
        default=None, pattern=r"^\d+(\.\d{1,6})?$"
    )
    note: str | None = None
    estimated_unit_price: Money | None = None
    estimated_unit_price_source_landed_cost_id: UUID | None = None


class PurchaseRequestLineInput(StrictApiModel):
    workspace_product_id: UUID
    quantity: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")
    note: str | None = None


class ApprovalStep(BaseModel):
    id: UUID
    assigned_membership_id: UUID
    source: ApprovalStepSource
    status: ApprovalStepStatus
    comment: str | None = None
    decided_by_membership_id: UUID | None = None
    decided_at: datetime | None = None


class PurchaseRequest(BaseModel):
    id: UUID
    branch_id: UUID
    cost_centre_id: UUID | None = None
    requested_by_membership_id: UUID
    required_by_date: date
    status: PurchaseRequestStatus
    lines: list[PurchaseRequestLine]
    estimated_total: Money | None = None
    has_incomplete_estimate: bool
    budget_status: BudgetStatus | None = None
    approval_step: ApprovalStep | None = None
    submitted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    delivered_at: datetime | None = None
    delivery_confirmed_by_membership_id: UUID | None = None
    has_delivery_discrepancy: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class PurchaseRequestCreate(StrictApiModel):
    branch_id: UUID
    cost_centre_id: UUID | None = None
    required_by_date: date
    lines: list[PurchaseRequestLineInput] = Field(min_length=1)


class PurchaseRequestUpdate(StrictApiModel):
    branch_id: UUID | None = None
    cost_centre_id: UUID | None = None
    required_by_date: date | None = None
    lines: list[PurchaseRequestLineInput] | None = Field(default=None, min_length=1)


class PurchaseRequestList(BaseModel):
    items: list[PurchaseRequest]
    next_cursor: str | None = None


class ApprovalDecisionInput(StrictApiModel):
    comment: str | None = None


class DeliveryConfirmationLineInput(StrictApiModel):
    purchase_request_line_id: UUID
    quantity_received: StrictStr = Field(pattern=r"^\d+(\.\d{1,6})?$")


class DeliveryConfirmationCreate(StrictApiModel):
    lines: list[DeliveryConfirmationLineInput] = Field(min_length=1)


class ThresholdRule(BaseModel):
    id: UUID
    branch_id: UUID | None = None
    min_amount: StrictStr = Field(pattern=r"^\d+(\.\d{1,4})?$")
    max_amount: StrictStr | None = Field(default=None, pattern=r"^\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    approver_membership_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None


class ThresholdRuleCreate(StrictApiModel):
    branch_id: UUID | None = None
    min_amount: StrictStr = Field(pattern=r"^\d+(\.\d{1,4})?$")
    max_amount: StrictStr | None = Field(default=None, pattern=r"^\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    approver_membership_id: UUID


class ThresholdRuleUpdate(StrictApiModel):
    branch_id: UUID | None = None
    min_amount: StrictStr | None = Field(default=None, pattern=r"^\d+(\.\d{1,4})?$")
    max_amount: StrictStr | None = Field(default=None, pattern=r"^\d+(\.\d{1,4})?$")
    currency: StrictStr | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    approver_membership_id: UUID | None = None


class ThresholdRuleList(BaseModel):
    items: list[ThresholdRule]
    next_cursor: str | None = None


class ApprovalDelegation(BaseModel):
    id: UUID
    delegator_membership_id: UUID
    delegate_membership_id: UUID
    starts_on: date
    ends_on: date
    created_at: datetime


class ApprovalDelegationCreate(StrictApiModel):
    delegator_membership_id: UUID | None = None
    delegate_membership_id: UUID
    starts_on: date
    ends_on: date


class ApprovalDelegationList(BaseModel):
    items: list[ApprovalDelegation]


class LowStockReport(BaseModel):
    id: UUID
    branch_id: UUID
    member_id: UUID
    workspace_product_id: UUID
    count_remaining: StrictStr | None = Field(
        default=None, pattern=r"^\d+(\.\d{1,6})?$"
    )
    created_at: datetime


class LowStockReportCreate(StrictApiModel):
    branch_id: UUID
    workspace_product_id: UUID
    count_remaining: StrictStr | None = Field(
        default=None, pattern=r"^\d+(\.\d{1,6})?$"
    )


class LowStockReportList(BaseModel):
    items: list[LowStockReport]
    next_cursor: str | None = None
