from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

type BudgetScope = Literal["organisation", "branch", "cost_centre"]
type BudgetPeriod = Literal["monthly", "quarterly", "annual"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^-?\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")


class Branch(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    region: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


class BranchCreate(StrictApiModel):
    name: str = Field(min_length=1)
    address: str | None = None
    region: str | None = None


class BranchUpdate(StrictApiModel):
    name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    region: str | None = None
    is_active: bool | None = None
    confirm_dependents: bool | None = None


class BranchList(BaseModel):
    items: list[Branch]
    next_cursor: str | None = None


class CostCentre(BaseModel):
    id: UUID
    name: str
    code: str
    budget_owner_membership_id: UUID | None = None
    branch_id: UUID | None = None
    is_orphaned: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime | None = None


class CostCentreCreate(StrictApiModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    budget_owner_membership_id: UUID | None = None
    branch_id: UUID | None = None


class CostCentreUpdate(StrictApiModel):
    name: str | None = Field(default=None, min_length=1)
    code: str | None = Field(default=None, min_length=1)
    budget_owner_membership_id: UUID | None = None
    branch_id: UUID | None = None
    is_archived: bool | None = None


class CostCentreList(BaseModel):
    items: list[CostCentre]
    next_cursor: str | None = None


class Budget(BaseModel):
    id: UUID
    amount: Money
    period: BudgetPeriod
    period_start: date
    scope: BudgetScope
    branch_id: UUID | None = None
    cost_centre_id: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime


class BudgetCreate(StrictApiModel):
    amount: StrictStr = Field(pattern=r"^\d+(\.\d{1,4})?$")
    currency: StrictStr = Field(pattern=r"^[A-Z]{3}$")
    period: BudgetPeriod
    period_start: date
    scope: BudgetScope
    branch_id: UUID | None = None
    cost_centre_id: UUID | None = None


class BudgetCreated(Budget):
    overlap_warning: bool = False


class BudgetList(BaseModel):
    items: list[Budget]
    next_cursor: str | None = None


class BranchRoleAssignment(BaseModel):
    id: UUID
    membership_id: UUID
    branch_id: UUID
    created_at: datetime


class BranchRoleAssignmentCreate(StrictApiModel):
    membership_id: UUID
    branch_id: UUID
