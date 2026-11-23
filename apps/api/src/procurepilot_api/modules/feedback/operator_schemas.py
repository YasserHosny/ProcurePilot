"""Request and response models for the platform-operator feedback endpoints (spec 025).

Operator-facing only: these carry the submitter's email, the operator labels and the workspace,
none of which a tenant-facing model may ever hold. `FeedbackStatus` and `FeedbackCategory` mirror
the database enums and the member API's models; they are defined here so this file has no
dependency on the member-side `schemas.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from procurepilot_api.modules.feedback.schemas import Category, Status
from procurepilot_api.modules.feedback.schemas import SignedUrl as SignedUrl  # re-exported

MAX_LABELS = 10
MAX_LABEL_LENGTH = 40


FeedbackStatus = Status
FeedbackCategory = Category


class OperatorAttachment(BaseModel):
    id: UUID
    kind: Literal["image", "audio"]
    content_type: str
    size_bytes: int
    display_order: int = Field(ge=0, le=4)


class OperatorSubmission(BaseModel):
    """One submission as an operator sees it: the tenant-facing fields plus the internal ones."""

    id: UUID
    tenant_id: UUID
    tenant_name: str | None = None
    text: str
    category: FeedbackCategory | None = None
    status: FeedbackStatus
    submitter_name: str
    submitter_email: str
    member_role: str
    page_path: str
    locale: Literal["en", "ar"]
    created_at: datetime
    labels: list[str] = Field(default_factory=list)
    app_version: str
    is_demo: bool
    status_changed_at: datetime | None = None
    attachments: list[OperatorAttachment] = Field(default_factory=list)


class OperatorSubmissionPage(BaseModel):
    items: list[OperatorSubmission]
    next_cursor: str | None = None
    total: int | None = Field(default=None, ge=0)


class OperatorMe(BaseModel):
    digest_enabled: bool
    digest_locale: Literal["en", "ar"]


class DigestPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    locale: Literal["en", "ar"] | None = None


class OperatorUpdateRequest(BaseModel):
    """PATCH body: a forward status move and/or a replacement label list. At least one field."""

    model_config = ConfigDict(extra="forbid")

    status: FeedbackStatus | None = None
    labels: list[str] | None = None

    @field_validator("labels")
    @classmethod
    def _normalise_labels(cls, labels: list[str] | None) -> list[str] | None:
        if labels is None:
            return None
        cleaned: list[str] = []
        for raw in labels:
            label = raw.strip()
            if not 1 <= len(label) <= MAX_LABEL_LENGTH:
                raise ValueError(f"each label must be 1 to {MAX_LABEL_LENGTH} characters")
            if label not in cleaned:
                cleaned.append(label)
        if len(cleaned) > MAX_LABELS:
            raise ValueError(f"at most {MAX_LABELS} labels")
        return cleaned

    @model_validator(mode="after")
    def _at_least_one_field(self) -> OperatorUpdateRequest:
        if self.status is None and self.labels is None:
            raise ValueError("provide status, labels, or both")
        return self
