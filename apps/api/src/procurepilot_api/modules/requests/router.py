from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.requests.schemas import (
    ApprovalDecisionInput,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestList,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
)
from procurepilot_api.modules.requests.service import (
    RequestsService,
    get_requests_service,
)

router = APIRouter(tags=["requests"])


@router.post(
    "/requests",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseRequest,
)
def create_request(
    payload: Annotated[PurchaseRequestCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    _idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> PurchaseRequest:
    return service.create_request(
        bearer_token=token, member=member, payload=payload
    )


@router.get("/requests", response_model=PurchaseRequestList)
def list_requests(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    status_filter: Annotated[
        PurchaseRequestStatus | None, Query(alias="status")
    ] = None,
    branch_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> PurchaseRequestList:
    return service.list_requests(
        bearer_token=token,
        status=status_filter,
        branch_id=branch_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/approvals/pending", response_model=PurchaseRequestList)
def list_pending_approvals(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> PurchaseRequestList:
    return service.list_pending_approvals(
        bearer_token=token,
        member=member,
        cursor=cursor,
        limit=limit,
    )


@router.get("/requests/{request_id}", response_model=PurchaseRequest)
def get_request(
    request_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> PurchaseRequest:
    return service.get_request(
        bearer_token=token, request_id=request_id
    )


@router.patch("/requests/{request_id}", response_model=PurchaseRequest)
def update_request(
    request_id: UUID,
    payload: Annotated[PurchaseRequestUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> PurchaseRequest:
    return service.update_request(
        bearer_token=token,
        member=member,
        request_id=request_id,
        patch=payload,
    )


@router.post(
    "/requests/{request_id}/submit",
    response_model=PurchaseRequest,
)
def submit_request(
    request_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    _idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> PurchaseRequest:
    return service.submit_request(
        bearer_token=token, member=member, request_id=request_id
    )


@router.post(
    "/requests/{request_id}/withdraw",
    response_model=PurchaseRequest,
)
def withdraw_request(
    request_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> PurchaseRequest:
    return service.withdraw_request(
        bearer_token=token, member=member, request_id=request_id
    )


@router.post(
    "/requests/{request_id}/approve",
    response_model=PurchaseRequest,
)
def approve_request(
    request_id: UUID,
    payload: Annotated[ApprovalDecisionInput, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> PurchaseRequest:
    return service.approve_request(
        bearer_token=token,
        member=member,
        request_id=request_id,
        payload=payload,
    )


@router.post(
    "/requests/{request_id}/reject",
    response_model=PurchaseRequest,
)
def reject_request(
    request_id: UUID,
    payload: Annotated[ApprovalDecisionInput, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> PurchaseRequest:
    return service.reject_request(
        bearer_token=token,
        member=member,
        request_id=request_id,
        payload=payload,
    )
