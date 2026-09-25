"""FastAPI router for the RFQ module (R4.3 Phase 3)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Request, status
from pydantic import BaseModel

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import PermissionDeniedError, UnprocessableEntityError
from procurepilot_api.modules.rfq.schemas import (
    AutoPreparationGuardrail,
    GuardrailCreateInput,
    GuardrailUpdateInput,
    PrepareRequestInput,
    PrepareRequestResponse,
    Rfq,
    RfqLine,
    RfqList,
    RfqRecipient,
    RfqResponseComparisonList,
)
from procurepilot_api.modules.rfq.service import RfqService, get_rfq_service
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(prefix="/rfq", tags=["rfq"])


def _rfq_create_limit() -> str:
    return get_settings().rate_limit_rfq_create


def _rfq_send_limit() -> str:
    return get_settings().rate_limit_rfq_send


class RfqLineCreate(BaseModel):
    workspace_product_id: uuid.UUID
    quantity: Decimal


class RfqCreatePayload(BaseModel):
    lines: list[RfqLineCreate]
    recipient_supplier_ids: list[uuid.UUID]
    needed_by_date: date
    tenant_terms: str | None = None


class RfqCreateResponse(BaseModel):
    rfq: Rfq
    lines: list[RfqLine]
    recipients: list[RfqRecipient]
    rejected_recipients: list[dict]


class RfqSendResponse(BaseModel):
    rfq: Rfq
    recipients: list[RfqRecipient]


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=RfqList,
    operation_id="listRfqs",
)
def list_rfqs(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> RfqList:
    return service.list_rfqs(
        member=member,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RfqCreateResponse,
    operation_id="createRfq",
)
@mutation_limiter.limit(_rfq_create_limit)
def create_rfq(
    request: Request,
    payload: Annotated[RfqCreatePayload, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> RfqCreateResponse:
    if idempotency_key is None:
        raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})

    rfq, lines, recipients, rejected_recipients = service.create(
        member=member,
        lines_data=payload.lines,
        recipient_supplier_ids=payload.recipient_supplier_ids,
        needed_by_date=payload.needed_by_date,
        idempotency_key=idempotency_key,
        tenant_terms=payload.tenant_terms,
    )

    return RfqCreateResponse(
        rfq=rfq,
        lines=lines,
        recipients=recipients,
        rejected_recipients=rejected_recipients,
    )


@router.post(
    "/{rfq_id}/send",
    status_code=status.HTTP_200_OK,
    response_model=RfqSendResponse,
    operation_id="sendRfq",
)
@mutation_limiter.limit(_rfq_send_limit)
def send_rfq(
    request: Request,
    rfq_id: uuid.UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> RfqSendResponse:
    if idempotency_key is None:
        raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})

    rfq, recipients = service.send(
        member=member,
        rfq_id=rfq_id,
        idempotency_key=idempotency_key,
    )
    return RfqSendResponse(rfq=rfq, recipients=recipients)


@router.get(
    "/{rfq_id}/responses",
    status_code=status.HTTP_200_OK,
    response_model=RfqResponseComparisonList,
    operation_id="listRfqResponses",
)
def list_responses(
    rfq_id: uuid.UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> RfqResponseComparisonList:
    return service.list_responses(
        member=member,
        rfq_id=rfq_id,
    )


@router.post(
    "/{rfq_id}/prepare-request",
    status_code=status.HTTP_201_CREATED,
    response_model=PrepareRequestResponse,
    operation_id="prepareRequestFromRfq",
)
@mutation_limiter.limit(_rfq_create_limit)
def prepare_request(
    request: Request,
    rfq_id: uuid.UUID,
    payload: Annotated[PrepareRequestInput, Body()],
    token: Annotated[str, Depends(bearer_token)],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> PrepareRequestResponse:
    if idempotency_key is None:
        raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})

    return service.prepare_request(
        bearer_token=token,
        member=member,
        rfq_id=rfq_id,
        rfq_response_id=payload.rfq_response_id,
        branch_id=payload.branch_id,
        cost_centre_id=payload.cost_centre_id,
        required_by_date=payload.required_by_date,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/guardrails",
    status_code=status.HTTP_201_CREATED,
    response_model=AutoPreparationGuardrail,
    operation_id="createGuardrail",
)
def create_guardrail(
    payload: Annotated[GuardrailCreateInput, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> AutoPreparationGuardrail:
    if member.role != "owner":
        raise PermissionDeniedError(details={"role": "owner_required"})

    if payload.max_order_value_amount <= Decimal("0"):
        raise UnprocessableEntityError(details={"max_order_value_amount": "Must be greater than 0"})

    return service.create_guardrail(member=member, payload=payload)


@router.get(
    "/guardrails",
    status_code=status.HTTP_200_OK,
    response_model=list[AutoPreparationGuardrail],
    operation_id="listGuardrails",
)
def list_guardrails(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> list[AutoPreparationGuardrail]:
    if member.role != "owner":
        raise PermissionDeniedError(details={"role": "owner_required"})

    return service.list_guardrails(member=member)


@router.patch(
    "/guardrails/{guardrail_id}",
    status_code=status.HTTP_200_OK,
    response_model=AutoPreparationGuardrail,
    operation_id="updateGuardrail",
)
def update_guardrail(
    guardrail_id: uuid.UUID,
    payload: Annotated[GuardrailUpdateInput, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[RfqService, Depends(get_rfq_service)],
) -> AutoPreparationGuardrail:
    if member.role != "owner":
        raise PermissionDeniedError(details={"role": "owner_required"})

    if payload.max_order_value_amount is not None and payload.max_order_value_amount <= Decimal(
        "0"
    ):
        raise UnprocessableEntityError(details={"max_order_value_amount": "Must be greater than 0"})

    return service.update_guardrail(member=member, guardrail_id=guardrail_id, payload=payload)
