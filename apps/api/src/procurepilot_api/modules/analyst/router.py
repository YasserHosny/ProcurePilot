"""FastAPI router for the Grounded Procurement Analyst module (R4.2).

T014: POST /analyst/conversations — create a conversation + first turn in one call.
T015: Per-member rate limiting via the existing SlowAPI mutation_limiter (same pattern
      as exports/router.py and catalogue/router.py).

Access: any active tenant member may call the ask-question endpoint (FR-009 restricts
*read* to creator/owner/buyer, not who may ask). No role restriction on this mutation.

Idempotency-Key is required on the mutation (consistent with every other mutation in
the codebase — see negotiation_briefs, exports, etc.).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Request, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.analyst.schemas import (
    AnalystConversationCreate,
    AnalystConversationResponse,
)
from procurepilot_api.modules.analyst.service import AnalystService, get_analyst_service
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(prefix="/analyst", tags=["analyst"])


def _analyst_ask_limit() -> str:
    # Evaluated per-request so tests can monkeypatch get_settings() and see the
    # new limit take effect immediately — same pattern as exports/router.py.
    return get_settings().rate_limit_analyst_ask


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=AnalystConversationResponse,
    operation_id="askAnalystQuestion",
)
@mutation_limiter.limit(_analyst_ask_limit)
def ask_question(
    request: Request,
    payload: Annotated[AnalystConversationCreate, Body()],
    member: Annotated[CurrentMember, Depends(current_member)],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[AnalystService, Depends(get_analyst_service)],
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
) -> AnalystConversationResponse:
    """Create a new analyst conversation with the first question answered in one call.

    Any active tenant member may call this endpoint (FR-009).
    Idempotency-Key is required to prevent duplicate turns on retry.
    """
    if idempotency_key is None:
        raise UnprocessableEntityError(details={"header": "Idempotency-Key is required"})
    return service.ask(
        member=member,
        question_text=payload.question_text,
        idempotency_key=idempotency_key,
        bearer_token=token,
        conversation_id=None,
        prior_turn_context=None,
    )
