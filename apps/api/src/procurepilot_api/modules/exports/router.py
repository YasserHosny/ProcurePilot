from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Request, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportDownloadUrl, ExportJob
from procurepilot_api.modules.exports.service import ExportService, get_export_service
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(tags=["exports"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


def _export_create_limit() -> str:
    # Evaluated per-request (slowapi supports a callable limit value), not once at import time,
    # so a test can monkeypatch get_settings() and see the new limit take effect immediately.
    return get_settings().rate_limit_export_create


@router.post("/exports", status_code=status.HTTP_202_ACCEPTED, response_model=ExportJob)
@mutation_limiter.limit(_export_create_limit)
def create_export(
    request: Request,
    payload: Annotated[ExportCreate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ExportService, Depends(get_export_service)],
    token: Annotated[str, Depends(bearer_token)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> ExportJob:
    return service.create_job(member=member, payload=payload, bearer_token=token)


@router.get("/exports/{id}", response_model=ExportJob)
def get_export(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ExportService, Depends(get_export_service)],
) -> ExportJob:
    return service.get_job(member=member, job_id=id)


@router.get("/exports/{id}/download", response_model=ExportDownloadUrl)
def download_export(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[ExportService, Depends(get_export_service)],
) -> ExportDownloadUrl:
    return ExportDownloadUrl(
        download_url=service.create_download_url(member=member, job_id=id, bearer_token=token)
    )
