"""Router for POS and inventory integration endpoints (R3.2).

No `from __future__ import annotations` here, deliberately — matching ingestion/router.py
and accounting/router.py. A slowapi @mutation_limiter.limit() decorator combined with
deferred (stringified) annotations breaks FastAPI/pydantic's forward-ref resolution for
plain Path/Query parameters.
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.pos.schemas import (
    PosConnection,
    StartConnectionResponse,
)
from procurepilot_api.modules.pos.service import (
    ConnectionService,
    get_connection_service,
)

router = APIRouter(prefix="/pos", tags=["pos"])
OWNER = (MemberRole.owner,)


def _frontend_redirect_url(
    settings: Settings,
    *,
    success: bool,
    error: str | None = None,
) -> str:
    """Build redirect URL to the web app's POS connection-settings screen.

    Route and query param match the frontend contract:
    ConnectionSettingsComponent is mounted at /pos and reads
    `pos_connected` = 'success' | 'failed'.
    """
    base = settings.api_cors_origins[0] if settings.api_cors_origins else settings.web_api_base_url
    base = base.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-7]
    params: dict[str, str] = {"pos_connected": "success" if success else "failed"}
    if error:
        params["error"] = error
    return f"{base}/pos?{urlencode(params)}"


@router.post(
    "/connect",
    response_model=StartConnectionResponse,
    operation_id="startPosConnection",
)
def start_connection(
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> StartConnectionResponse:
    url = service.connect(member)
    return StartConnectionResponse(authorization_url=url)


@router.get(
    "/connect/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    operation_id="completePosConnection",
)
def complete_connection_callback(
    state: Annotated[str, Query()],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    row = service.complete_connection(
        state=state,
        code=code,
        error=error,
    )
    if row is None:
        return RedirectResponse(
            url=_frontend_redirect_url(
                settings,
                success=False,
                error=error or "authorization_failed",
            ),
            status_code=status.HTTP_302_FOUND,
        )
    return RedirectResponse(
        url=_frontend_redirect_url(settings, success=True),
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/connection",
    response_model=PosConnection,
    operation_id="getPosConnection",
)
def get_pos_connection(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> PosConnection:
    row = service.get_status(member)
    if row is None:
        raise NotFoundError(details={"resource": "pos_connection"})
    return PosConnection.model_validate(row)


@router.post(
    "/disconnect",
    response_model=PosConnection,
    operation_id="disconnectPos",
)
def disconnect_pos(
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> PosConnection:
    row = service.disconnect(member, bearer_token=token)
    return PosConnection.model_validate(row)
