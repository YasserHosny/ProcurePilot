"""Member and owner feedback endpoints (spec 025, contracts/feedback.openapi.yaml).

Any workspace role may submit and read its own items. The workspace inbox is owner-only and
answers 404, not 403, to everyone else. Tenancy comes from the verified token; nothing here
reads a tenant, role or user from the request body, path or query.
"""

# No `from __future__ import annotations` here, deliberately: slowapi's decorator wraps the
# endpoint, and FastAPI could then no longer resolve string annotations against this module.
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.schemas import (
    Category,
    SignedUrl,
    Status,
    Submission,
    SubmissionPage,
)
from procurepilot_api.modules.feedback.service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    FeedbackService,
    get_feedback_service,
)
from procurepilot_api.modules.feedback.validation import UploadedFile
from procurepilot_api.shared.rate_limit import mutation_limiter

router = APIRouter(prefix="/feedback", tags=["feedback"])

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"model": Submission, "description": "Idempotent replay of an earlier request"},
    413: {"description": "A file is too large"},
    415: {"description": "A file's content is not an allowed type"},
    422: {"description": "Validation failed"},
    429: {"description": "Cooldown (feedback.cooldown) or rate limit"},
}


def _submit_limit() -> str:
    return get_settings().rate_limit_feedback_submit


def owner_or_not_found(
    member: Annotated[CurrentMember, Depends(current_member)],
) -> CurrentMember:
    """The workspace inbox is for the owner only; everyone else is told it does not exist."""
    if member.role != MemberRole.owner:
        raise NotFoundError(details={"resource": "feedback"})
    return member


async def _read_upload(file: UploadFile | str, limit: int) -> UploadedFile | None:
    # A browser sends an unnamed, empty part for an untouched file input; Starlette delivers it
    # as a plain empty string rather than an UploadFile. Anything else that is not a file is
    # refused.
    if isinstance(file, str):
        if file == "":
            return None
        raise UnprocessableEntityError(details={"reason": "expected_file"})
    # One byte past the limit is enough for validation to answer 413 without buffering a
    # much larger file.
    content = await file.read(limit + 1)
    if not content and not file.filename:
        return None
    return UploadedFile(
        filename=file.filename or "file",
        content=content,
        declared_content_type=file.content_type,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Submission,
    responses=_ERROR_RESPONSES,
    operation_id="submitFeedback",
)
@mutation_limiter.limit(_submit_limit)
async def submit_feedback(
    request: Request,
    response: Response,
    member: Annotated[CurrentMember, Depends(current_member)],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    text: Annotated[str, Form()],
    category: Annotated[Category | None, Form()] = None,
    images: Annotated[list[UploadFile | str] | None, File()] = None,
    audio: Annotated[UploadFile | str | None, File()] = None,
    referer: Annotated[str | None, Header()] = None,
    accept_language: Annotated[str | None, Header()] = None,
) -> Submission:
    # FastAPI keeps one value for a single-valued part; a second voice message must be refused,
    # not silently dropped. The parsed form is cached on the request, so this reads no body twice.
    form = await request.form()
    audio_parts = [part for part in form.getlist("audio") if part != ""]
    if len(audio_parts) > 1:
        raise UnprocessableEntityError(details={"reason": "too_many_audio", "max": 1})

    uploaded_images: list[UploadedFile] = []
    for image in images or []:
        part = await _read_upload(image, settings.feedback_image_max_bytes)
        if part is not None:
            uploaded_images.append(part)
    uploaded_audio = (
        await _read_upload(audio, settings.feedback_audio_max_bytes) if audio is not None else None
    )
    result = await run_in_threadpool(
        service.submit,
        member=member,
        bearer_token=token,
        idempotency_key=idempotency_key,
        text=text,
        category=category,
        images=uploaded_images,
        audio=uploaded_audio,
        referer=referer,
        accept_language=accept_language,
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.submission


@router.get("", response_model=SubmissionPage, operation_id="listWorkspaceFeedback")
def list_workspace_feedback(
    member: Annotated[CurrentMember, Depends(owner_or_not_found)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    category: Category | None = None,
) -> SubmissionPage:
    return service.list_workspace(
        member=member, cursor=cursor, limit=limit, status=status_filter, category=category
    )


# Registered before "/{submission_id}" so "mine" is never read as an id.
@router.get("/mine", response_model=SubmissionPage, operation_id="listMyFeedback")
def list_my_feedback(
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> SubmissionPage:
    return service.list_mine(member=member, cursor=cursor, limit=limit)


@router.get("/{submission_id}", response_model=Submission, operation_id="getFeedback")
def get_feedback(
    submission_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> Submission:
    return service.get(member=member, submission_id=submission_id)


@router.delete(
    "/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="withdrawFeedback",
    responses={409: {"description": "Status is no longer `new` (feedback.withdraw_refused)"}},
)
def withdraw_feedback(
    submission_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    token: Annotated[str, Depends(bearer_token)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> Response:
    service.withdraw(member=member, bearer_token=token, submission_id=submission_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{submission_id}/attachments/{attachment_id}/url",
    response_model=SignedUrl,
    operation_id="getAttachmentUrl",
)
def get_attachment_url(
    submission_id: UUID,
    attachment_id: UUID,
    member: Annotated[CurrentMember, Depends(current_member)],
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> SignedUrl:
    return service.attachment_url(
        member=member, submission_id=submission_id, attachment_id=attachment_id
    )
