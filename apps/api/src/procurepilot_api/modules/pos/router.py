"""Router for POS and inventory integration endpoints (R3.2).

No `from __future__ import annotations` here, deliberately — matching ingestion/router.py
and accounting/router.py. A slowapi @mutation_limiter.limit() decorator combined with
deferred (stringified) annotations breaks FastAPI/pydantic's forward-ref resolution for
plain Path/Query parameters.
"""

from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.pos.schemas import (
    ManualMatchRequest,
    PosConnection,
    PosProductMatch,
    StartConnectionResponse,
    SyncedProductSignalList,
    TriggerSyncResponse,
)
from procurepilot_api.modules.pos.service import (
    ConnectionService,
    get_connection_service,
)
from procurepilot_api.modules.pos.sync_service import (
    ConnectionNotActiveError,
    SyncService,
    TokenRefreshFailedError,
)
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(prefix="/pos", tags=["pos"])
OWNER = (MemberRole.owner,)
SYNC_ROLES = (MemberRole.owner, MemberRole.buyer)
MATCH_ROLES = (MemberRole.owner, MemberRole.buyer)


def _pos_sync_limit() -> str:
    return get_settings().rate_limit_pos_sync


def _pos_match_limit() -> str:
    return get_settings().rate_limit_pos_match


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


@router.post(
    "/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TriggerSyncResponse,
    operation_id="triggerPosSync",
)
@mutation_limiter.limit(_pos_sync_limit)
def trigger_pos_sync(
    request: Request,
    member: Annotated[CurrentMember, Depends(require_role(*SYNC_ROLES))],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TriggerSyncResponse:
    conn_row = service.get_status(member)
    if conn_row is None or conn_row.get("status") != "active":
        raise NotFoundError(
            details={
                "resource": "pos_connection",
                "reason": "no_active_connection",
            }
        )

    connection_id = UUID(str(conn_row["id"]))
    sync_service = SyncService(settings=settings)
    try:
        sync_service.sync(
            settings,
            tenant_id=member.tenant_id,
            connection_id=connection_id,
        )
    except ConnectionNotActiveError as exc:
        raise NotFoundError(
            details={
                "resource": "pos_connection",
                "reason": "connection_not_active",
                "status": exc.status,
            }
        ) from exc
    except TokenRefreshFailedError as exc:
        raise NotFoundError(
            details={
                "resource": "pos_connection",
                "reason": "token_refresh_failed",
            }
        ) from exc

    return TriggerSyncResponse(status="enqueued")


@router.get(
    "/signals",
    response_model=SyncedProductSignalList,
    operation_id="listSyncedProductSignals",
)
def list_synced_product_signals(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    match_status: Annotated[Literal["matched", "unmatched"] | None, Query()] = None,
    workspace_product_id: Annotated[UUID | None, Query()] = None,
) -> SyncedProductSignalList:
    return service.list_signals(
        member,
        cursor=cursor,
        limit=limit,
        match_status=match_status,
        workspace_product_id=workspace_product_id,
    )


@router.post(
    "/signals/{signal_id}/match",
    response_model=PosProductMatch,
    operation_id="manuallyMatchProductSignal",
)
@mutation_limiter.limit(_pos_match_limit)
def manually_match_product_signal(
    request: Request,
    signal_id: UUID,
    payload: ManualMatchRequest,
    member: Annotated[CurrentMember, Depends(require_role(*MATCH_ROLES))],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    token: Annotated[str, Depends(bearer_token)],
) -> PosProductMatch:
    return service.manual_match(
        member,
        signal_id=signal_id,
        workspace_product_id=payload.workspace_product_id,
        bearer_token=token,
    )
