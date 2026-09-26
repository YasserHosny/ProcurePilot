from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

DocumentSourceChannel = Literal["upload", "email", "capture", "catalogue_import"]
DocumentStatus = Literal["uploaded", "failed_to_read"]


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresignRequest(StrictApiModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal[
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]
    size_bytes: int = Field(ge=1)
    content_hash: StrictStr | None = None


class PotentialDuplicate(BaseModel):
    quotation_id: UUID
    document_id: UUID
    created_at: datetime
    supplier_name: str | None = None
    stated_total_amount: str | None = None
    stated_total_currency: str | None = None


class PresignResponse(BaseModel):
    document_id: UUID
    storage_bucket: str
    storage_path: str
    upload_url: str
    upload_fields: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    potential_duplicates: list[PotentialDuplicate] = Field(default_factory=list)


class DownloadUrlResponse(BaseModel):
    download_url: str


class Document(BaseModel):
    id: UUID
    storage_bucket: str
    storage_path: str
    mime_type: str
    content_hash: str | None = None
    source_channel: DocumentSourceChannel
    status: DocumentStatus
    created_at: datetime
    created_by: UUID
