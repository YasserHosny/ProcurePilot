from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, status

from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.savings.evidence import EvidenceService, get_evidence_service
from procurepilot_api.modules.savings.schemas import (
    PurchaseOutcomeCreate,
    PurchaseOutcomeCreated,
    SavingEvidence,
    SavingList,
    SavingRecord,
)
from procurepilot_api.modules.savings.service import SavingsService, get_savings_service

router = APIRouter(tags=["savings"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post(
    "/purchases",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOutcomeCreated,
)
def record_purchase(
    payload: Annotated[PurchaseOutcomeCreate, Body()],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[SavingsService, Depends(get_savings_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> PurchaseOutcomeCreated:
    return service.record_purchase(member=member, payload=payload)


@router.get("/savings", response_model=SavingList)
def list_savings(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[SavingsService, Depends(get_savings_service)],
    saving_status: Annotated[Literal["pending", "verified"] | None, Query(alias="status")] = None,
    period_start: Annotated[date | None, Query()] = None,
    period_end: Annotated[date | None, Query()] = None,
    supplier_id: Annotated[UUID | None, Query()] = None,
    branch_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SavingList:
    return service.list_savings(
        member=member,
        status=saving_status,
        period_start=period_start,
        period_end=period_end,
        supplier_id=supplier_id,
        branch_id=branch_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/savings/{id}", response_model=SavingRecord)
def get_saving(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[SavingsService, Depends(get_savings_service)],
) -> SavingRecord:
    return service.get_saving(member=member, saving_id=id)


@router.get("/savings/{id}/evidence", response_model=SavingEvidence)
def get_evidence(
    id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> SavingEvidence:
    return service.get_evidence(member=member, saving_id=id)


@router.post("/savings/{id}/verify", response_model=SavingRecord)
def verify_saving(
    id: UUID,
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[SavingsService, Depends(get_savings_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> SavingRecord:
    return service.verify_saving(member=member, saving_id=id)
