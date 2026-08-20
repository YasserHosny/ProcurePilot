from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Job(BaseModel):
    id: UUID
    quotation_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    attempted_provider: Literal["structured_parse", "bedrock", "azure_di"] | None = None
    error: dict[str, object] | None = None
    result_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
