from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, status

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportJob
from procurepilot_api.modules.exports.service import ExportService, get_export_service

router = APIRouter(tags=["exports"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post("/exports", status_code=status.HTTP_202_ACCEPTED, response_model=ExportJob)
def create_export(
    payload: Annotated[ExportCreate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ExportService, Depends(get_export_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> ExportJob:
    return service.create_job(member=member, payload=payload)


@router.get("/exports/{id}", response_model=ExportJob)
def get_export(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ExportService, Depends(get_export_service)],
) -> ExportJob:
    return service.get_job(member=member, job_id=id)
