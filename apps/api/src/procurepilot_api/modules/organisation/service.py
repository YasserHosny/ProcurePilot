from __future__ import annotations

from procurepilot_api.config import Settings, get_settings


class OrganisationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()


def get_organisation_service() -> OrganisationService:
    return OrganisationService()
