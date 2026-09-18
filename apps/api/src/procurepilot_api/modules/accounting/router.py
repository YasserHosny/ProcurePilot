"""Router for accounting integration endpoints (R3.1)."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.accounting.reconciliation_service import (
    ReconciliationService,
    get_reconciliation_service,
)
from procurepilot_api.modules.accounting.schemas import (
    AccountingConnection,
    ReconciliationDiscrepancy,
    ReconciliationDiscrepancyList,
    ResolveDiscrepancyRequest,
    StartConnectionResponse,
    SyncedBillList,
    TriggerSyncResponse,
)
from procurepilot_api.modules.accounting.service import (
    ConnectionService,
    get_connection_service,
)
from procurepilot_api.modules.accounting.sync_service import (
    ConnectionNotActiveError,
    SyncService,
    TokenRefreshFailedError,
)
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role

router = APIRouter(prefix="/accounting", tags=["accounting"])
OWNER = (MemberRole.owner,)
SYNC_ROLES = (MemberRole.owner, MemberRole.buyer)



def _frontend_redirect_url(
    settings: Settings,
    *,
    success: bool,
    error: str | None = None,
) -> str:
    """Build redirect URL to the web app's connection-settings screen.

    Route and query param match the frontend's own contract exactly:
    ConnectionSettingsComponent is mounted at /accounting (see app.routes.ts) and reads
    `accounting_connected` = 'success' | 'failed' (see handleOAuthCallbackParams).
    """
    base = settings.api_cors_origins[0] if settings.api_cors_origins else settings.web_api_base_url
    base = base.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-7]
    params: dict[str, str] = {"accounting_connected": "success" if success else "failed"}
    if error:
        params["error"] = error
    return f"{base}/accounting?{urlencode(params)}"


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


@router.post(
    "/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TriggerSyncResponse,
    operation_id="triggerAccountingSync",
)
def trigger_accounting_sync(
    member: Annotated[CurrentMember, Depends(require_role(*SYNC_ROLES))],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TriggerSyncResponse:
    # 1. Look up the tenant's current connection via tenant-scoped service.
    # Translate missing or non-active connections to NotFoundError (404) per OpenAPI contract.
    conn_row = service.get_status(member)
    if conn_row is None or conn_row.get("status") != "active":
        raise NotFoundError(
            details={
                "resource": "accounting_connection",
                "reason": "no_active_connection",
            }
        )

    connection_id = UUID(str(conn_row["id"]))

    # 2. Synchronous execution: There is no background task queue for manual sync triggers
    # in this codebase. The daily worker handles recurring synchronization. The manual
    # trigger completes inline within the HTTP request and returns 202 Accepted ("enqueued"
    # per OpenAPI contract) as an intentional simplification.
    sync_service = SyncService()
    try:
        sync_service.sync(
            settings,
            tenant_id=member.tenant_id,
            connection_id=connection_id,
        )
    except ConnectionNotActiveError as exc:
        # Contract documents 404 for no active connection (including disconnected/needs_reauth).
        raise NotFoundError(
            details={
                "resource": "accounting_connection",
                "reason": "connection_not_active",
                "status": exc.status,
            }
        ) from exc
    except TokenRefreshFailedError as exc:
        # Token refresh failed during sync; SyncService has already transitioned connection status
        # to 'needs_reauth' and recorded the audit event. Mapping to NotFoundError (404) preserves
        # the small OpenAPI contract surface (which documents 404 for "no active connection").
        raise NotFoundError(
            details={
                "resource": "accounting_connection",
                "reason": "token_refresh_failed",
            }
        ) from exc
    # Note: ConflictError (raised by SyncService when Postgres advisory lock cannot be acquired)
    # is an AppError subclass and is automatically translated to HTTP 409 Conflict by the global
    # exception handler.

    # Returns {"status": "enqueued"} with 202 Accepted per the OpenAPI contract, interpreting
    # "enqueued" loosely as accepted and processed.
    return TriggerSyncResponse(status="enqueued")


@router.get(
    "/bills",
    response_model=SyncedBillList,
    operation_id="listSyncedBills",
)
def list_synced_bills(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ConnectionService, Depends(get_connection_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    match_status: Annotated[Literal["matched", "unmatched"] | None, Query()] = None,
) -> SyncedBillList:
    return service.list_bills(
        member,
        cursor=cursor,
        limit=limit,
        match_status=match_status,
    )


@router.get(
    "/discrepancies",
    response_model=ReconciliationDiscrepancyList,
    operation_id="listReconciliationDiscrepancies",
)
def list_reconciliation_discrepancies(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Annotated[Literal["open", "resolved"], Query()] = "open",
) -> ReconciliationDiscrepancyList:
    return service.list_discrepancies(
        member,
        cursor=cursor,
        limit=limit,
        status=status,
    )


@router.post(
    "/discrepancies/{discrepancy_id}/resolve",
    response_model=ReconciliationDiscrepancy,
    operation_id="resolveReconciliationDiscrepancy",
)
def resolve_reconciliation_discrepancy(
    discrepancy_id: UUID,
    member: Annotated[CurrentMember, Depends(require_role(*SYNC_ROLES))],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[ReconciliationService, Depends(get_reconciliation_service)],
    body: ResolveDiscrepancyRequest | None = None,
) -> ReconciliationDiscrepancy:
    note = body.note if body else None
    result = service.resolve(
        member,
        discrepancy_id=discrepancy_id,
        note=note,
        bearer_token=token,
    )
    return ReconciliationDiscrepancy.model_validate(result)

