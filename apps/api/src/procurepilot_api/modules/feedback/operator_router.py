"""Platform-operator feedback endpoints under /platform/feedback (spec 025, US5).

Every route depends on `current_operator`: a verified JWT plus a live `platform_operator` lookup on
each request. A caller who is not an active operator receives the same 404 as an unknown route.
`/me` and `/digest-preference` are declared before `/{id}` so they are never read as an id.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from procurepilot_api.modules.auth.operator import CurrentOperator, current_operator
from procurepilot_api.modules.feedback.operator_schemas import (
    DigestPreferenceRequest,
    FeedbackCategory,
    FeedbackStatus,
    OperatorMe,
    OperatorSubmission,
    OperatorSubmissionPage,
    OperatorUpdateRequest,
    SignedUrl,
)
from procurepilot_api.modules.feedback.operator_service import (
    OperatorFeedbackService,
    get_operator_feedback_service,
)

router = APIRouter(prefix="/platform/feedback", tags=["platform-operator"])

Operator = Annotated[CurrentOperator, Depends(current_operator)]
Service = Annotated[OperatorFeedbackService, Depends(get_operator_feedback_service)]


@router.get("", response_model=OperatorSubmissionPage)
def list_feedback(
    operator: Operator,
    service: Service,
    status: Annotated[FeedbackStatus | None, Query()] = None,
    category: Annotated[FeedbackCategory | None, Query()] = None,
    tenant_id: Annotated[UUID | None, Query()] = None,
    is_demo: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OperatorSubmissionPage:
    return service.list_feedback(
        operator,
        status=status,
        category=category,
        tenant_id=tenant_id,
        is_demo=is_demo,
        cursor=cursor,
        limit=limit,
    )


@router.get("/me", response_model=OperatorMe)
def operator_me(operator: Operator, service: Service) -> OperatorMe:
    return service.me(operator)


@router.put("/digest-preference", response_model=OperatorMe)
def set_digest_preference(
    body: DigestPreferenceRequest,
    operator: Operator,
    service: Service,
) -> OperatorMe:
    return service.set_digest_preference(operator, enabled=body.enabled, locale=body.locale)


@router.get("/{id}", response_model=OperatorSubmission)
def get_feedback(id: UUID, operator: Operator, service: Service) -> OperatorSubmission:
    return service.get_feedback(operator, id)


@router.patch("/{id}", response_model=OperatorSubmission)
def update_feedback(
    id: UUID,
    body: OperatorUpdateRequest,
    operator: Operator,
    service: Service,
) -> OperatorSubmission:
    return service.update_feedback(operator, id, status=body.status, labels=body.labels)


@router.get("/{id}/attachments/{attachment_id}/url", response_model=SignedUrl)
def get_attachment_url(
    id: UUID,
    attachment_id: UUID,
    operator: Operator,
    service: Service,
) -> SignedUrl:
    return service.attachment_url(operator, id, attachment_id)
