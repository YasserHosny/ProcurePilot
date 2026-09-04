from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.documents.schemas import (
    Document,
    DownloadUrlResponse,
    PresignRequest,
    PresignResponse,
)
from procurepilot_api.modules.documents.service import DocumentService, get_document_service

router = APIRouter(tags=["documents"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post(
    "/documents/presign",
    status_code=status.HTTP_201_CREATED,
    response_model=PresignResponse,
)
def presign_document_upload(
    payload: Annotated[PresignRequest, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[DocumentService, Depends(get_document_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> PresignResponse:
    return service.create_presigned_upload(bearer_token=token, member=member, payload=payload)


@router.get("/documents/{document_id}", response_model=Document)
def get_document(
    document_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Document:
    return service.get_document(bearer_token=token, document_id=document_id)


@router.get("/documents/{document_id}/download", response_model=DownloadUrlResponse)
def get_document_download_url(
    document_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DownloadUrlResponse:
    return service.create_download_url(bearer_token=token, document_id=document_id)
