from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReportKind = Literal["savings_ledger", "spend_by_supplier", "alerts_summary"]
ReportFormat = Literal["csv", "xlsx", "pdf"]
ScheduleStatus = Literal["active", "paused"]
ArtifactStatus = Literal["queued", "running", "completed", "failed", "expired"]
ReportLocale = Literal["en", "ar"]


class ReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: UUID | None = None
    branch_id: UUID | None = None


def validate_kind_format_matrix(kind: str, format: str) -> None:
    if kind == "spend_by_supplier" and format == "pdf":
        raise ValueError("pdf is not offered for spend_by_supplier")


class ReportScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReportKind
    format: ReportFormat
    filters: ReportFilters = Field(default_factory=ReportFilters)
    weekday: int = Field(ge=0, le=6)
    locale: ReportLocale | None = None

    @model_validator(mode="after")
    def validate_matrix(self) -> ReportScheduleCreate:
        validate_kind_format_matrix(self.kind, self.format)
        return self


class ReportScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ReportFormat | None = None
    filters: ReportFilters | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    locale: ReportLocale | None = None
    status: ScheduleStatus | None = None


class ReportSchedule(BaseModel):
    id: UUID
    kind: ReportKind
    format: ReportFormat
    filters: ReportFilters
    weekday: int
    status: ScheduleStatus
    next_run_at: datetime
    last_run_at: datetime | None = None
    rule_version: str = ""
    locale: ReportLocale
    created_at: datetime
    updated_at: datetime


class ReportScheduleList(BaseModel):
    items: list[ReportSchedule]
    next_cursor: str | None = None


class ReportArtifactFilters(BaseModel):
    model_config = ConfigDict(extra="allow")

    period_start: str | None = None
    period_end: str | None = None
    supplier_id: str | None = None
    branch_id: str | None = None


class ReportArtifact(BaseModel):
    id: UUID
    kind: ReportKind
    format: ReportFormat
    filters: ReportArtifactFilters
    status: ArtifactStatus
    row_count: int | None = Field(default=None, ge=0)
    rule_version: str = ""
    schedule_id: UUID | None = None
    locale: ReportLocale
    download_url: str | None = None
    expires_at: datetime | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ReportArtifactList(BaseModel):
    items: list[ReportArtifact]
    next_cursor: str | None = None
