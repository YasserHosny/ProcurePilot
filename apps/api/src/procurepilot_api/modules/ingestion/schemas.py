from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IngestionEmailStatus = Literal[
    "received", "processing", "completed", "failed", "duplicate", "rejected"
]
SupplierMatchMethod = Literal["address", "domain", "thread", "manual"]


class TenantEmailConfig(BaseModel):
    id: UUID
    forwarding_address: str
    enabled: bool
    domain_allowlist: list[str] | None
    daily_limit: int
    daily_count: int
    daily_count_date: date
    spf_dkim_required: bool
    created_at: datetime
    updated_at: datetime


class TenantEmailConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    domain_allowlist: list[str] | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=10_000)
    spf_dkim_required: bool | None = None


class IngestionEmailLog(BaseModel):
    id: UUID
    message_id: str
    from_address: str
    from_domain: str
    subject: str | None
    received_at: datetime
    processed_at: datetime | None
    status: IngestionEmailStatus
    error_message: str | None
    attachment_count: int
    quotation_id: UUID | None
    supplier_id: UUID | None
    match_method: SupplierMatchMethod | None
    created_at: datetime


class IngestionEmailLogList(BaseModel):
    items: list[IngestionEmailLog]
    next_cursor: str | None


CatalogueImportStatus = Literal["pending", "processing", "completed", "failed"]


class CatalogueImportSummary(BaseModel):
    id: UUID
    supplier_id: UUID
    file_name: str
    file_path: str
    file_size_bytes: int
    file_format: Literal["csv", "xlsx"]
    status: CatalogueImportStatus
    total_rows: int | None = None
    imported_rows: int | None = None
    skipped_rows: int | None = None
    error_rows: int | None = None
    error_details: list[dict[str, Any]] = Field(default_factory=list)
    column_mapping: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None
    created_by: UUID


class CatalogueImportSummaryList(BaseModel):
    items: list[CatalogueImportSummary]
    next_cursor: str | None = None


class IngestionStats(BaseModel):
    emails_received_today: int
    emails_received_week: int
    emails_received_month: int
    capture_uploads_total: int
    catalogue_imports_total: int
    supplier_match_rate: float
    extraction_success_rate: float
