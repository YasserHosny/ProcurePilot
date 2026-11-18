"""Attachment validation for feedback submissions (spec 025, research D5).

Files are judged by their bytes (libmagic), never by file name or the declared content type.
Order of refusal: count (422), then per file size (413) and type (415), so a huge wrong file is
refused as too large before anything parses it.

Audio note (T041 findings, see tests/fixtures/feedback/README.md): libmagic reports audio-only
`MediaRecorder` output as `video/webm` (Chrome, Firefox) and `video/mp4` (Safari, Chrome). Those
two container types are therefore accepted only after the container itself shows audio and no
video, and are stored under the audio types.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import magic

from procurepilot_api.config import Settings
from procurepilot_api.errors import (
    PayloadTooLargeError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)

type AttachmentKind = Literal["image", "audio"]

# libmagic report -> type we store. Several spellings exist across libmagic releases.
_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}

_AUDIO_TYPES: dict[str, str] = {
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/x-mp3": "audio/mpeg",
    "audio/x-wav": "audio/wav",
    "audio/wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/mp4": "audio/mp4",
    "audio/webm": "audio/webm",
}

# Containers libmagic reports as video even when they hold only audio; accepted after a check.
_AUDIO_IN_VIDEO_CONTAINER: dict[str, str] = {
    "video/webm": "audio/webm",
    "video/mp4": "audio/mp4",
}

_WEBM_VIDEO_CODECS = (
    b"V_VP8",
    b"V_VP9",
    b"V_AV1",
    b"V_THEORA",
    b"V_MPEG4/",
    b"V_MPEG2",
    b"V_MPEGH/",
    b"V_MS/VFW/FOURCC",
)
_WEBM_AUDIO_CODECS = (b"A_OPUS", b"A_VORBIS", b"A_AAC", b"A_FLAC", b"A_PCM", b"A_MPEG/")
_MP4_HANDLER = re.compile(rb"hdlr.{8}(.{4})", re.DOTALL)


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes
    declared_content_type: str | None = None


@dataclass(frozen=True)
class ValidatedAttachment:
    kind: AttachmentKind
    filename: str
    content: bytes
    content_type: str
    size_bytes: int
    display_order: int


def _detect(content: bytes) -> str:
    return magic.from_buffer(content, mime=True)


def _refused(detected: str, kind: str, name: str | None) -> UnsupportedMediaTypeError:
    # The file name is the member's own; returning it lets the widget say which file to remove.
    details: dict[str, object] = {"detected_mime": detected, "kind": kind}
    if name:
        details["name"] = name
    return UnsupportedMediaTypeError(details=details)


def sniff_image(content: bytes, name: str | None = None) -> str:
    detected = _detect(content)
    stored = _IMAGE_TYPES.get(detected)
    if stored is None:
        raise _refused(detected, "image", name)
    return stored


def _mp4_is_audio_only(content: bytes) -> bool:
    handlers = {match.group(1) for match in _MP4_HANDLER.finditer(content)}
    return b"soun" in handlers and b"vide" not in handlers


def _webm_is_audio_only(content: bytes) -> bool:
    has_audio = any(codec in content for codec in _WEBM_AUDIO_CODECS)
    has_video = any(codec in content for codec in _WEBM_VIDEO_CODECS)
    return has_audio and not has_video


def sniff_audio(content: bytes, name: str | None = None) -> str:
    detected = _detect(content)
    stored = _AUDIO_TYPES.get(detected)
    if stored is not None:
        return stored
    container = _AUDIO_IN_VIDEO_CONTAINER.get(detected)
    if container == "audio/mp4" and _mp4_is_audio_only(content):
        return container
    if container == "audio/webm" and _webm_is_audio_only(content):
        return container
    raise _refused(detected, "audio", name)


def _check_size(file: UploadedFile, limit: int, kind: AttachmentKind) -> None:
    size = len(file.content)
    if size == 0:
        raise UnprocessableEntityError(details={"reason": "empty_file", "kind": kind})
    if size > limit:
        raise PayloadTooLargeError(details={"kind": kind, "max_bytes": limit})


def validate_attachments(
    images: Sequence[UploadedFile],
    audio: UploadedFile | None,
    settings: Settings,
) -> list[ValidatedAttachment]:
    """Validate every file before any is stored; raises on the first problem found."""
    if len(images) > settings.feedback_image_max_count:
        raise UnprocessableEntityError(
            details={"reason": "too_many_images", "max": settings.feedback_image_max_count}
        )
    validated: list[ValidatedAttachment] = []
    for order, image in enumerate(images):
        _check_size(image, settings.feedback_image_max_bytes, "image")
        validated.append(
            ValidatedAttachment(
                kind="image",
                filename=image.filename,
                content=image.content,
                content_type=sniff_image(image.content, image.filename),
                size_bytes=len(image.content),
                display_order=order,
            )
        )
    if audio is not None:
        _check_size(audio, settings.feedback_audio_max_bytes, "audio")
        validated.append(
            ValidatedAttachment(
                kind="audio",
                filename=audio.filename,
                content=audio.content,
                content_type=sniff_audio(audio.content, audio.filename),
                size_bytes=len(audio.content),
                display_order=0,
            )
        )
    return validated
