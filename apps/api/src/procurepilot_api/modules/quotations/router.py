from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, status
from fastapi.responses import StreamingResponse

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.quotations.confirmation_service import (
    QuotationConfirmationService,
    get_quotation_confirmation_service,
)
from procurepilot_api.modules.quotations.review_service import (
    QuotationReviewService,
    get_quotation_review_service,
)
from procurepilot_api.modules.quotations.schemas import (
    ConfirmRequest,
    Quotation,
    QuotationCreate,
    QuotationDetail,
    QuotationReviewPatch,
    RefuseRequest,
    ReviewTaskList,
    ReviewTaskPriority,
)
from procurepilot_api.modules.quotations.service import QuotationService, get_quotation_service

router = APIRouter(tags=["quotations"])
WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)


@router.post("/quotations", status_code=status.HTTP_201_CREATED, response_model=Quotation)
def create_quotation(
    payload: Annotated[QuotationCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    return service.create_quotation(bearer_token=token, member=member, payload=payload)


@router.get("/quotations/{quotation_id}", response_model=QuotationDetail)
def get_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
) -> QuotationDetail:
    return service.get_quotation(bearer_token=token, quotation_id=quotation_id)


@router.post("/quotations/{quotation_id}/archive", response_model=Quotation)
def archive_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    return service.archive_quotation(
        bearer_token=token, member=member, quotation_id=quotation_id
    )


@router.post("/quotations/{quotation_id}/restore", response_model=Quotation)
def restore_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    return service.restore_quotation(
        bearer_token=token, member=member, quotation_id=quotation_id
    )


@router.post("/quotations/{quotation_id}/retry-extraction", response_model=Quotation)
def retry_extraction(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    return service.retry_extraction(
        bearer_token=token, member=member, quotation_id=quotation_id
    )


@router.get("/quotations/{quotation_id}/export")
def export_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    format: Annotated[Literal["csv"], Query()] = "csv",
) -> StreamingResponse:
    csv_body = service.export_quotation_csv(
        bearer_token=token, member=member, quotation_id=quotation_id
    )
    return StreamingResponse(
        iter([csv_body]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="quotation-{quotation_id}.csv"'
            )
        },
    )


@router.patch("/quotations/{quotation_id}", response_model=QuotationDetail)
def patch_quotation_review(
    quotation_id: UUID,
    payload: Annotated[QuotationReviewPatch, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationReviewService, Depends(get_quotation_review_service)],
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> QuotationDetail:
    return service.apply_review_patch(
        bearer_token=token, member=member, quotation_id=quotation_id, patch=payload
    )


@router.post("/quotations/{quotation_id}/confirm", response_model=Quotation)
def confirm_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationConfirmationService, Depends(get_quotation_confirmation_service)],
    payload: Annotated[ConfirmRequest | None, Body()] = None,
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    return service.confirm(
        bearer_token=token, member=member, quotation_id=quotation_id, payload=payload
    )


@router.post("/quotations/{quotation_id}/refuse", response_model=Quotation)
def refuse_quotation(
    quotation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(require_role(*WRITE_ROLES))],
    service: Annotated[QuotationReviewService, Depends(get_quotation_review_service)],
    payload: Annotated[RefuseRequest | None, Body()] = None,
    _idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> Quotation:
    from procurepilot_api.modules.quotations.service import _quotation

    row = service.refuse_quotation(
        bearer_token=token,
        member=member,
        quotation_id=quotation_id,
        reason=payload.reason if payload else None,
    )
    return _quotation(row)


@router.get("/review-tasks", response_model=ReviewTaskList)
def list_review_tasks(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[QuotationService, Depends(get_quotation_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
    status: Annotated[Literal["open", "in_progress", "resolved", "all"], Query()] = "open",
    priority: Annotated[ReviewTaskPriority | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    sort_by: Annotated[
        Literal["created_at", "stated_total", "priority", "status"], Query()
    ] = "created_at",
    sort_order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> ReviewTaskList:
    return service.list_review_tasks(
        bearer_token=token,
        cursor=cursor,
        limit=limit,
        status=status,
        priority=priority,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
