from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WorkerSettings:
    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "quotation-extraction"
    provider_mode: Literal["stub", "bedrock", "azure_di"] = "stub"
    confidence_threshold: float = 0.85


def get_settings() -> WorkerSettings:
    return WorkerSettings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
        ),
        supabase_url=os.environ.get("SUPABASE_URL", "http://localhost:54321"),
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        queue_name=os.environ.get("EXTRACTION_QUEUE_NAME", "quotation-extraction"),
        provider_mode=os.environ.get("EXTRACTION_PROVIDER_MODE", "stub"),
        confidence_threshold=float(os.environ.get("EXTRACTION_CONFIDENCE_THRESHOLD", "0.85")),
    )
