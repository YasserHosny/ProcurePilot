from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IngestionEmailStatus = Literal[
    "received", "processing", "completed", "failed", "duplicate", "rejected"
]
SupplierMatchMethod = Literal["address", "domain", "thread", "manual", "rfq_reply"]


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

CatalogueRefreshReviewStatus = Literal["pending_review", "processing", "approved", "rejected"]


class CatalogueRefreshReview(BaseModel):
    id: UUID
    refresh_schedule_id: UUID
    source_import_id: UUID
    supplier_id: UUID
    status: CatalogueRefreshReviewStatus
    normalized_rows: list[dict[str, Any]]
    errors: list[dict[str, Any] | str]
    row_count: int
    error_count: int
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    source_file_name: str
    source_file_format: Literal["csv", "xlsx"]


class CatalogueRefreshReviewDecision(BaseModel):
    review_id: UUID
    status: Literal["approved", "rejected"]
    catalogue_import_id: UUID | None = None
    supplier_id: UUID | None = None
    imported_rows: int | None = None
    error_rows: int | None = None


class CatalogueRefreshReviewList(BaseModel):
    items: list[CatalogueRefreshReview]
    next_cursor: str | None = None


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
    active_quotation_count: int
    integration_sourced_quotation_count: int
    integration_sourced_share: float
    purchase_history_days: int
    g3_history_ready: bool
    active_refresh_schedule_count: int
    linked_refresh_schedule_count: int
    refresh_pilot_ready: bool
