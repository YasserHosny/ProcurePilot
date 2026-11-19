"""Response models for in-app feedback (spec 025, contracts/feedback.openapi.yaml).

`Submission` is the tenant-facing view and deliberately has no `labels` field: operator labels
are internal and never shown to submitters or owners. The operator models extend it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from procurepilot_api.modules.auth.jwt import MemberRole


class Category(StrEnum):
    bug = "bug"
    idea = "idea"
    question = "question"
    other = "other"


class Status(StrEnum):
    new = "new"
    reviewed = "reviewed"
    resolved = "resolved"


class AttachmentKind(StrEnum):
    image = "image"
    audio = "audio"


class Attachment(BaseModel):
    id: UUID
    kind: AttachmentKind
    content_type: str
    size_bytes: int
    display_order: int = Field(ge=0, le=4)


class Submission(BaseModel):
    """Tenant-facing view. Never includes operator labels."""

    id: UUID
    text: str
    category: Category | None = None
    status: Status
    # Present in the owner inbox only.
    submitter_name: str | None = None
    member_role: MemberRole
    page_path: str
    locale: Literal["en", "ar"]
    created_at: datetime
    # True only for the submitter while the status is `new`.
    can_withdraw: bool = False
    attachments: list[Attachment]


class SubmissionPage(BaseModel):
    items: list[Submission]
    next_cursor: str | None = None


class SignedUrl(BaseModel):
    url: str
    expires_in: int
