from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Response, status

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.modules.requests.schemas import (
    ApprovalDecisionInput,
    ApprovalDelegation,
    ApprovalDelegationCreate,
    ApprovalDelegationList,
    LowStockReport,
    LowStockReportCreate,
    LowStockReportList,
    PurchaseRequest,
    PurchaseRequestCreate,
    PurchaseRequestList,
    PurchaseRequestStatus,
    PurchaseRequestUpdate,
    ThresholdRule,
    ThresholdRuleCreate,
    ThresholdRuleList,
    ThresholdRuleUpdate,
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
    response: Response,
    idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> PurchaseRequest:
    request, created = service.create_request(
        bearer_token=token,
        member=member,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return request


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


@router.post(
    "/low-stock-reports",
    status_code=status.HTTP_201_CREATED,
    response_model=LowStockReport,
)
def create_low_stock_report(
    payload: Annotated[LowStockReportCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    response: Response,
    idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> LowStockReport:
    report, created = service.create_low_stock_report(
        bearer_token=token,
        member=member,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return report


@router.get("/low-stock-reports", response_model=LowStockReportList)
def list_low_stock_reports(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    branch_id: Annotated[UUID | None, Query()] = None,
    workspace_product_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> LowStockReportList:
    return service.list_low_stock_reports(
        bearer_token=token,
        branch_id=branch_id,
        workspace_product_id=workspace_product_id,
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


@router.get("/approvals/threshold-rules", response_model=ThresholdRuleList)
def list_threshold_rules(
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
) -> ThresholdRuleList:
    return service.list_threshold_rules(
        bearer_token=token,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/approvals/threshold-rules",
    status_code=status.HTTP_201_CREATED,
    response_model=ThresholdRule,
)
def create_threshold_rule(
    payload: Annotated[ThresholdRuleCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    _idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ThresholdRule:
    return service.create_threshold_rule(
        bearer_token=token,
        member=member,
        payload=payload,
    )


@router.patch(
    "/approvals/threshold-rules/{rule_id}",
    response_model=ThresholdRule,
)
def update_threshold_rule(
    rule_id: UUID,
    payload: Annotated[ThresholdRuleUpdate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> ThresholdRule:
    return service.update_threshold_rule(
        bearer_token=token,
        member=member,
        rule_id=rule_id,
        patch=payload,
    )


@router.delete(
    "/approvals/threshold-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_threshold_rule(
    rule_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> None:
    service.delete_threshold_rule(
        bearer_token=token,
        member=member,
        rule_id=rule_id,
    )


@router.get("/approvals/delegations", response_model=ApprovalDelegationList)
def list_approval_delegations(
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    membership_id: Annotated[UUID | None, Query()] = None,
) -> ApprovalDelegationList:
    return service.list_approval_delegations(
        bearer_token=token,
        member=member,
        membership_id=membership_id,
    )


@router.post(
    "/approvals/delegations",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalDelegation,
)
def create_approval_delegation(
    payload: Annotated[ApprovalDelegationCreate, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
    _idempotency_key: Annotated[
        UUID | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ApprovalDelegation:
    return service.create_approval_delegation(
        bearer_token=token,
        member=member,
        payload=payload,
    )


@router.delete(
    "/approvals/delegations/{delegation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def cancel_approval_delegation(
    delegation_id: UUID,
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RequestsService, Depends(get_requests_service)],
) -> None:
    service.cancel_approval_delegation(
        bearer_token=token,
        member=member,
        delegation_id=delegation_id,
    )
