from __future__ import annotations

from procurepilot_api.config import Settings, get_settings


class RequestsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()


def get_requests_service() -> RequestsService:
    return RequestsService()
