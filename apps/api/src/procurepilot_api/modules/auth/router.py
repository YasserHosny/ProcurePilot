from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response, status

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import InvalidCredentialsError
from procurepilot_api.modules.auth.models import (
    LoginRequest,
    LogoutRequest,
    PasswordResetRequest,
    RefreshRequest,
)
from procurepilot_api.modules.auth.service import AuthService, get_auth_service
from procurepilot_api.modules.members.models import SessionResponse
from procurepilot_api.shared.audit import AuditEventCreate, AuditWriter, get_audit_writer
from procurepilot_api.shared.rate_limit import auth_rate_limit, limiter

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_LIMIT = auth_rate_limit(get_settings())


@router.post("/login", response_model=SessionResponse)
@limiter.limit(AUTH_LIMIT)
def login(
    request: Request,
    payload: Annotated[LoginRequest, Body()],
    service: Annotated[AuthService, Depends(get_auth_service)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> SessionResponse:
    try:
        return service.login(email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        audit.record(
            AuditEventCreate(
                actor_email=payload.email,
                action="auth.login_failed",
                outcome="refused",
                target={"email": payload.email},
            )
        )
        raise


@router.post("/refresh", response_model=SessionResponse)
@limiter.limit(AUTH_LIMIT)
def refresh(
    request: Request,
    payload: Annotated[RefreshRequest, Body()],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    """Exchange a refresh token for a new session once the access token has expired.

    Deliberately unauthenticated: the access token is usually already expired when this is
    called. The workspace is not chosen here — the access-token hook re-reads the caller's
    persisted active workspace at issuance, so the new token carries the same `tenant_id` claim
    the old one did (or none, if that membership has since been removed).
    """
    return service.reissue_session(refresh_token=payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_LIMIT)
def logout(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    _member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    payload: Annotated[LogoutRequest | None, Body()] = None,
) -> Response:
    if payload is not None and payload.refresh_token:
        service.logout(access_token=token, refresh_token=payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(AUTH_LIMIT)
def password_reset(
    request: Request,
    payload: Annotated[PasswordResetRequest, Body()],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    service.request_password_reset(email=payload.email)
    return Response(status_code=status.HTTP_202_ACCEPTED)
