"""Spec 025 T029 and T042 (unit part): attachment validation is by content, never by name.

Audio expectations come from running libmagic over real recorder output (T041). See the
fixture table in tests/fixtures/feedback/README.md and the notes in validation.py.
"""

from __future__ import annotations

import pytest
from integration.feedback_helpers import (
    GIF_BYTES,
    MIB,
    PDF_BYTES,
    SVG_BYTES,
    TEXT_BYTES,
    audio_fixture,
    jpeg_bytes,
    png_bytes,
    webp_bytes,
)

from procurepilot_api.config import Settings
from procurepilot_api.errors import (
    PayloadTooLargeError,
    UnprocessableEntityError,
    UnsupportedMediaTypeError,
)
from procurepilot_api.modules.feedback.validation import (
    UploadedFile,
    sniff_audio,
    sniff_image,
    validate_attachments,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _image(name: str, content: bytes) -> UploadedFile:
    return UploadedFile(filename=name, content=content, declared_content_type=None)


# ---------------------------------------------------------------- images


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (jpeg_bytes(), "image/jpeg"),
        (png_bytes(), "image/png"),
        (webp_bytes(), "image/webp"),
    ],
)
def test_image_content_types_are_sniffed(content: bytes, expected: str) -> None:
    assert sniff_image(content) == expected


@pytest.mark.parametrize(
    "content",
    [TEXT_BYTES, PDF_BYTES, GIF_BYTES, SVG_BYTES, audio_fixture("tone.wav"), b"\x00" * 64],
)
def test_non_allowed_content_is_rejected_whatever_the_name_says(content: bytes) -> None:
    with pytest.raises(UnsupportedMediaTypeError) as caught:
        sniff_image(content)
    assert "detected_mime" in (caught.value.details or {})


def test_renamed_text_file_is_rejected_even_with_an_image_extension_and_type(
    settings: Settings,
) -> None:
    upload = UploadedFile(
        filename="screenshot.png", content=TEXT_BYTES, declared_content_type="image/png"
    )
    with pytest.raises(UnsupportedMediaTypeError):
        validate_attachments([upload], None, settings)


def test_a_refused_file_is_named_in_the_error_details(settings: Settings) -> None:
    """The widget can then say which attachment to remove (T083 hosted walkthrough finding)."""
    uploads = [_image("ok.png", png_bytes()), _image("not-an-image.png", TEXT_BYTES)]
    with pytest.raises(UnsupportedMediaTypeError) as caught:
        validate_attachments(uploads, None, settings)
    assert (caught.value.details or {}).get("name") == "not-an-image.png"

    fake_audio = UploadedFile("voice.mp3", audio_fixture("renamed-fake.mp3"), "audio/mpeg")
    with pytest.raises(UnsupportedMediaTypeError) as caught:
        validate_attachments([], fake_audio, settings)
    assert (caught.value.details or {}).get("name") == "voice.mp3"


def test_valid_images_keep_order_and_report_the_sniffed_type_not_the_declared_one(
    settings: Settings,
) -> None:
    uploads = [
        UploadedFile("a.bin", jpeg_bytes(), "application/octet-stream"),
        UploadedFile("b.jpg", png_bytes(), "image/jpeg"),
        UploadedFile("c", webp_bytes(), None),
    ]
    result = validate_attachments(uploads, None, settings)
    assert [(a.kind, a.display_order, a.content_type) for a in result] == [
        ("image", 0, "image/jpeg"),
        ("image", 1, "image/png"),
        ("image", 2, "image/webp"),
    ]
    assert [a.size_bytes for a in result] == [len(u.content) for u in uploads]


def test_image_at_exactly_5_mib_is_accepted_and_one_byte_over_is_413(settings: Settings) -> None:
    exactly = jpeg_bytes(extra=5 * MIB - len(jpeg_bytes()))
    assert len(exactly) == 5 * MIB
    assert validate_attachments([_image("ok.jpg", exactly)], None, settings)

    with pytest.raises(PayloadTooLargeError):
        validate_attachments([_image("big.jpg", exactly + b"\x00")], None, settings)


def test_size_is_checked_before_type_so_a_huge_wrong_file_is_413(settings: Settings) -> None:
    with pytest.raises(PayloadTooLargeError):
        validate_attachments([_image("big.png", TEXT_BYTES * 200_000)], None, settings)


def test_five_images_are_accepted_and_a_sixth_is_422(settings: Settings) -> None:
    five = [_image(f"{i}.jpg", jpeg_bytes()) for i in range(5)]
    assert len(validate_attachments(five, None, settings)) == 5

    with pytest.raises(UnprocessableEntityError) as caught:
        validate_attachments([*five, _image("6.jpg", jpeg_bytes())], None, settings)
    assert (caught.value.details or {}).get("reason") == "too_many_images"


def test_count_limit_is_checked_before_content(settings: Settings) -> None:
    # Six wrong files: the refusal is about the count, and nothing is read as an image.
    six = [_image(f"{i}.png", TEXT_BYTES) for i in range(6)]
    with pytest.raises(UnprocessableEntityError):
        validate_attachments(six, None, settings)


def test_empty_file_is_422(settings: Settings) -> None:
    with pytest.raises(UnprocessableEntityError) as caught:
        validate_attachments([_image("empty.jpg", b"")], None, settings)
    assert (caught.value.details or {}).get("reason") == "empty_file"


def test_limits_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEEDBACK_IMAGE_MAX_COUNT", "2")
    monkeypatch.setenv("FEEDBACK_IMAGE_MAX_BYTES", "100")
    small = Settings()
    assert validate_attachments([_image("a.jpg", jpeg_bytes())], None, small)
    with pytest.raises(UnprocessableEntityError):
        validate_attachments([_image(f"{i}.jpg", jpeg_bytes()) for i in range(3)], None, small)
    with pytest.raises(PayloadTooLargeError):
        validate_attachments([_image("a.jpg", jpeg_bytes(extra=200))], None, small)


# ---------------------------------------------------------------- audio

# fixture -> (what libmagic reported, canonical type we store). Both columns are asserted so a
# libmagic upgrade that changes a report fails here, not in production.
AUDIO_CASES = [
    ("recorded-chrome.webm", "video/webm", "audio/webm"),  # real Chrome 156 MediaRecorder output
    ("recorded-chrome.mp4", "video/mp4", "audio/mp4"),  # real Chrome 156, audio/mp4 AAC
    ("recorded-safari-style.mp4", "video/mp4", "audio/mp4"),  # Chrome file, ftyp brand 'mp42'
    ("voice.m4a", "audio/x-m4a", "audio/mp4"),  # Chrome file, ftyp brand 'M4A '
    ("silence.mp3", "audio/mpeg", "audio/mpeg"),  # hand-built MPEG-1 L3 frames behind ID3v2
    ("tone.wav", "audio/x-wav", "audio/wav"),  # python wave module
]


@pytest.mark.parametrize(("name", "libmagic_type", "stored_type"), AUDIO_CASES)
def test_audio_fixtures_are_accepted_and_normalised(
    name: str, libmagic_type: str, stored_type: str
) -> None:
    import magic

    content = audio_fixture(name)
    assert magic.from_buffer(content, mime=True) == libmagic_type
    assert sniff_audio(content) == stored_type


def test_audio_is_stored_as_kind_audio_with_order_zero(settings: Settings) -> None:
    upload = UploadedFile("note.webm", audio_fixture("recorded-chrome.webm"), "audio/webm")
    (attachment,) = validate_attachments([], upload, settings)
    assert (attachment.kind, attachment.display_order, attachment.content_type) == (
        "audio",
        0,
        "audio/webm",
    )


def test_renamed_fake_audio_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        sniff_audio(audio_fixture("renamed-fake.mp3"))


@pytest.mark.parametrize("content", [jpeg_bytes(), png_bytes(), PDF_BYTES, b"\x00" * 64])
def test_non_audio_content_is_rejected_as_audio(content: bytes) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        sniff_audio(content)


def test_an_mp4_with_a_video_track_is_not_audio() -> None:
    # libmagic says video/mp4 for audio-only recordings too, so the container is inspected: the
    # handler of every track must be 'soun'. Flipping the Chrome file's handler makes it video.
    content = audio_fixture("recorded-chrome.mp4").replace(b"soun", b"vide")
    with pytest.raises(UnsupportedMediaTypeError):
        sniff_audio(content)


def test_a_webm_with_a_video_codec_is_not_audio() -> None:
    content = audio_fixture("recorded-chrome.webm") + b"V_VP9"
    with pytest.raises(UnsupportedMediaTypeError):
        sniff_audio(content)


def test_a_mp4_with_no_audio_track_at_all_is_not_audio() -> None:
    content = audio_fixture("recorded-chrome.mp4").replace(b"soun", b"meta")
    with pytest.raises(UnsupportedMediaTypeError):
        sniff_audio(content)


def test_audio_at_exactly_10_mib_is_accepted_and_one_byte_over_is_413(settings: Settings) -> None:
    base = audio_fixture("tone.wav")
    exactly = base + b"\x00" * (10 * MIB - len(base))
    assert len(exactly) == 10 * MIB
    assert validate_attachments([], UploadedFile("a.wav", exactly, None), settings)
    with pytest.raises(PayloadTooLargeError):
        validate_attachments([], UploadedFile("a.wav", exactly + b"\x00", None), settings)


def test_images_and_audio_validate_together(settings: Settings) -> None:
    result = validate_attachments(
        [_image("a.jpg", jpeg_bytes()), _image("b.png", png_bytes())],
        UploadedFile("n.mp3", audio_fixture("silence.mp3"), None),
        settings,
    )
    assert [a.kind for a in result] == ["image", "image", "audio"]
