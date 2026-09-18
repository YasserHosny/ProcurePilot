"""Router for accounting integration endpoints (R3.1)."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.accounting.schemas import (
    AccountingConnection,
    StartConnectionResponse,
)
from procurepilot_api.modules.accounting.service import (
    ConnectionService,
    get_connection_service,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

router = APIRouter(prefix="/accounting", tags=["accounting"])
OWNER = (MemberRole.owner,)


def _frontend_redirect_url(
    settings: Settings,
    *,
    success: bool,
    error: str | None = None,
) -> str:
    """Build redirect URL to the web app's connection-settings screen."""
    base = settings.api_cors_origins[0] if settings.api_cors_origins else settings.web_api_base_url
    base = base.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-7]
    params: dict[str, str] = {
        "status": "success" if success else "error",
        "success": "true" if success else "false",
    }
    if error:
        params["error"] = error
    return f"{base}/accounting/connection-settings?{urlencode(params)}"


@router.post(
    "/connect",
    response_model=StartConnectionResponse,
    operation_id="startAccountingConnection",
)
def start_connection(
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> StartConnectionResponse:
    url = service.start_connection(member)
    return StartConnectionResponse(authorization_url=url)


@router.get(
    "/connect/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    operation_id="completeAccountingConnection",
)
def complete_connection_callback(
    state: Annotated[str, Query()],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str | None, Query()] = None,
    realm_id: Annotated[str | None, Query(alias="realmId")] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    row = service.complete_connection(
        state=state,
        code=code,
        realm_id=realm_id,
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
    response_model=AccountingConnection,
    operation_id="getAccountingConnection",
)
def get_accounting_connection(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> AccountingConnection:
    row = service.get_status(member)
    if row is None:
        raise NotFoundError(details={"resource": "accounting_connection"})
    return AccountingConnection.model_validate(row)


@router.post(
    "/disconnect",
    response_model=AccountingConnection,
    operation_id="disconnectAccounting",
)
def disconnect_accounting(
    member: Annotated[CurrentMember, Depends(require_role(*OWNER))],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
) -> AccountingConnection:
    row = service.disconnect(member, bearer_token=token)
    return AccountingConnection.model_validate(row)
