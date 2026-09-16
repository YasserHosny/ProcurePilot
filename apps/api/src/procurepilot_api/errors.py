from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from procurepilot_api.shared.logging import get_trace_id, redact

logger = logging.getLogger(__name__)

type ErrorDetails = dict[str, object] | list[dict[str, object]] | None


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: ErrorDetails = None
    trace_id: str = Field(min_length=1)


class AppError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"
    safe_message = "Request could not be completed."

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details
        super().__init__(self.safe_message)


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "auth.unauthenticated"
    safe_message = "Authentication failed."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "auth.permission_denied"
    safe_message = "Action is not permitted."


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "auth.invalid_credentials"
    safe_message = "Authentication failed."


class InvitationRefusedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "invitation.refused"
    safe_message = "Invitation is not valid."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    safe_message = "Resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    safe_message = "Request conflicts with the current state."


class UnprocessableEntityError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation.invalid_value"
    safe_message = "Request validation failed."


class ExportRowCapExceededError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "export_row_cap_exceeded"
    safe_message = "Request validation failed."


class ScheduleCapExceededError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "report_schedule_cap_exceeded"
    safe_message = "Request validation failed."


class DigestSubscriptionCapExceededError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "digest_subscription_cap_exceeded"
    safe_message = "Request validation failed."


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "validation.unsupported_media_type"
    safe_message = "File type is not supported."


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"
    safe_message = "Service is unavailable."


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    app_error = _coerce_app_error(exc)
    return _error_response(
        status_code=app_error.status_code,
        code=app_error.code,
        message=app_error.safe_message,
        details=app_error.details,
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    validation_error = _coerce_validation_error(exc)
    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation.invalid_request",
        message="Request validation failed.",
        details=_validation_details(validation_error.errors()),
    )


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    http_error = _coerce_http_error(exc)
    status_code = http_error.status_code
    code = "not_found" if status_code == status.HTTP_404_NOT_FOUND else "http_error"
    message = (
        "Resource was not found." if status_code == status.HTTP_404_NOT_FOUND else "Request failed."
    )
    return _error_response(status_code=status_code, code=code, message=message, details=None)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request exception",
        extra={"path": request.url.path, "method": request.method},
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="Request could not be completed.",
        details=None,
    )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: ErrorDetails,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        details=details,
        trace_id=get_trace_id(),
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def _validation_details(errors: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for error in errors:
        details.append(
            {
                "loc": list(error.get("loc", ())),
                "msg": redact(str(error.get("msg", "Invalid value."))),
                "type": str(error.get("type", "value_error")),
            }
        )
    return details


def _coerce_app_error(exc: Exception) -> AppError:
    if isinstance(exc, AppError):
        return exc
    return AppError()


def _coerce_validation_error(exc: Exception) -> RequestValidationError:
    if isinstance(exc, RequestValidationError):
        return exc
    raise TypeError("Expected RequestValidationError")


def _coerce_http_error(exc: Exception) -> StarletteHTTPException:
    if isinstance(exc, StarletteHTTPException):
        return exc
    raise TypeError("Expected StarletteHTTPException")
