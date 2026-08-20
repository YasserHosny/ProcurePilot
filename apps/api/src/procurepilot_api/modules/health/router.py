from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.errors import ServiceUnavailableError

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    client = _probe_client(settings)
    try:
        client.table("supported_region").select("code").limit(1).execute()
    except Exception as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return HealthResponse(status="ok")


def _probe_client(settings: Settings) -> Client:
    # The anon key suffices: supported_region is readable by anon, and a successful select proves
    # the round-trip. Using the service-role key here would put an RLS bypass in an unauthenticated
    # endpoint for no benefit.
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key.get_secret_value(),
    )
