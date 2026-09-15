from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExportKind = Literal["savings_ledger", "spend_by_supplier", "alerts_summary"]
ExportFormat = Literal["csv", "xlsx", "pdf"]
ExportStatus = Literal["queued", "running", "completed", "failed", "expired"]
ExportLocale = Literal["en", "ar"]


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date | None = None
    supplier_id: UUID | None = None
    branch_id: UUID | None = None

    @model_validator(mode="after")
    def validate_range(self) -> ExportFilters:
        if self.period_end is not None and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExportKind
    format: ExportFormat
    filters: ExportFilters
    locale: ExportLocale | None = None

    @model_validator(mode="after")
    def validate_matrix(self) -> ExportCreate:
        if self.kind == "spend_by_supplier" and self.format == "pdf":
            raise ValueError("pdf is not offered for spend_by_supplier")
        return self


class ExportDownloadUrl(BaseModel):
    download_url: str


class ExportJob(BaseModel):
    id: UUID
    kind: ExportKind
    format: ExportFormat
    filters: ExportFilters
    status: ExportStatus
    locale: ExportLocale | None = None
    row_count: int | None = Field(default=None, ge=0)
    download_url: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
