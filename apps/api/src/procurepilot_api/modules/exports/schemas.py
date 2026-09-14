from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date
    supplier_id: UUID | None = None
    branch_id: UUID | None = None

    @model_validator(mode="after")
    def validate_range(self) -> ExportFilters:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["savings_ledger"]
    format: Literal["xlsx", "pdf"]
    filters: ExportFilters


class ExportDownloadUrl(BaseModel):
    download_url: str


class ExportJob(BaseModel):
    id: UUID
    kind: Literal["savings_ledger"]
    format: Literal["xlsx", "pdf"]
    filters: ExportFilters
    status: Literal["queued", "running", "completed", "failed"]
    row_count: int | None = Field(default=None, ge=0)
    download_url: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
