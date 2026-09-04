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
    log_level: str = "info"
    aws_region: str = "us-east-1"
    aws_profile: str = ""
    bedrock_model_id: str = "arn:aws:bedrock:us-east-1:524256002093:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0"
    azure_di_endpoint: str = ""
    azure_di_key: str = ""


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
        aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_profile=os.environ.get("AWS_PROFILE", ""),
        bedrock_model_id=os.environ.get(
            "BEDROCK_MODEL_ID",
            "arn:aws:bedrock:us-east-1:524256002093:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        ),
        azure_di_endpoint=os.environ.get("AZURE_DI_ENDPOINT", ""),
        azure_di_key=os.environ.get("AZURE_DI_KEY", ""),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
