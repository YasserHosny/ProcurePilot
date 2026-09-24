"""FastAPI router for the RFQ module (R4.3 Phase 3)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Request, status
from pydantic import BaseModel

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.rfq.schemas import Rfq, RfqLine, RfqRecipient
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
