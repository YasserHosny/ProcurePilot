from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status

from procurepilot_api.deps import CurrentMember, bearer_token
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.extraction.service import ExtractionService, get_extraction_service
from procurepilot_api.modules.jobs.schemas import Job

router = APIRouter(tags=["extraction"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post(
    "/quotations/{quotation_id}/extract",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Job,
)
def extract_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[ExtractionService, Depends(get_extraction_service)],
    response: Response,
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Job:
    job, created = service.enqueue_extraction(
        bearer_token=token,
        member=member,
        quotation_id=quotation_id,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return job
