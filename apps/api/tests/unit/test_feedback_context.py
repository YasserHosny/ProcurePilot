"""Spec 025 T020 / research D3: request context for a feedback submission.

Page address comes from the Referer and language from Accept-Language. Both originate in the
browser, so both are validated and used for triage context only, never for authorisation.
"""

from __future__ import annotations

import pytest

from procurepilot_api.config import Settings
from procurepilot_api.modules.feedback.context import (
    MAX_PAGE_PATH_CHARS,
    allowed_web_origins,
    locale_from_accept_language,
    page_path_from_referer,
)

ORIGINS = ("http://localhost:4200", "https://app.procurepilot.test")


@pytest.mark.parametrize(
    ("referer", "expected"),
    [
        ("http://localhost:4200/requests/123", "/requests/123"),
        ("http://localhost:4200/requests/123?tab=lines&x=1", "/requests/123?tab=lines&x=1"),
        # A fragment never reaches the server in a real Referer; if one is present it is dropped.
        ("http://localhost:4200/requests/123?tab=a#frag", "/requests/123?tab=a"),
        ("https://app.procurepilot.test/orders", "/orders"),
        ("http://localhost:4200", "/"),
        ("http://localhost:4200/", "/"),
        # Origins compare case-insensitively on scheme and host.
        ("HTTP://LOCALHOST:4200/Home", "/Home"),
    ],
)
def test_same_origin_referer_becomes_path_and_query(referer: str, expected: str) -> None:
    assert page_path_from_referer(referer, ORIGINS) == expected


def test_path_and_query_are_capped_at_2000_characters() -> None:
    long_query = "q=" + "a" * 5000
    value = page_path_from_referer(f"http://localhost:4200/search?{long_query}", ORIGINS)
    assert len(value) == MAX_PAGE_PATH_CHARS == 2000
    assert value.startswith("/search?q=aaa")


@pytest.mark.parametrize(
    "referer",
    [
        "https://evil.example/requests/1",
        # Same host, different scheme or port is a different origin.
        "https://localhost:4200/requests/1",
        "http://localhost:4201/requests/1",
        # Userinfo trick: the real host is evil.example.
        "http://localhost:4200@evil.example/requests/1",
        # Suffix trick.
        "http://localhost:4200.evil.example/requests/1",
        "javascript:alert(1)",
        "data:text/html,hello",
        "//evil.example/x",
        "/relative/path",
        "not a url",
        "",
        None,
    ],
)
def test_foreign_or_malformed_referer_is_rejected(referer: str | None) -> None:
    assert page_path_from_referer(referer, ORIGINS) == ""


def test_no_allowed_origin_means_nothing_is_accepted() -> None:
    assert page_path_from_referer("http://localhost:4200/x", ()) == ""


def test_control_characters_are_removed_from_the_stored_path() -> None:
    value = page_path_from_referer("http://localhost:4200/a\r\nb\x00c?x=1\t2", ORIGINS)
    assert value == "/abc?x=12"


@pytest.mark.parametrize(
    ("header", "default", "expected"),
    [
        ("ar", "en", "ar"),
        ("en", "ar", "en"),
        ("ar-EG,ar;q=0.9,en;q=0.8", "en", "ar"),
        ("en-US,en;q=0.9,ar;q=0.8", "ar", "en"),
        ("AR-sa", "en", "ar"),
        # Highest q wins even when listed later.
        ("en;q=0.3, ar;q=0.9", "en", "ar"),
        # Unsupported languages are skipped, a supported later one is used.
        ("fr-FR,fr;q=0.9,ar;q=0.5", "en", "ar"),
        # q=0 means "not acceptable".
        ("ar;q=0, en;q=0.2", "ar", "en"),
        # Nothing usable: tenant default.
        ("fr-FR,fr;q=0.9", "ar", "ar"),
        ("fr-FR,fr;q=0.9", "en", "en"),
        ("*", "ar", "ar"),
        (None, "ar", "ar"),
        ("", "en", "en"),
        # Garbage and bad q-values never raise.
        ("en;q=abc", "ar", "en"),
        (";;;,,,", "ar", "ar"),
        ("x" * 5000, "ar", "ar"),
    ],
)
def test_accept_language_is_normalised_to_en_or_ar(
    header: str | None, default: str, expected: str
) -> None:
    assert locale_from_accept_language(header, default) == expected


def test_default_outside_en_ar_falls_back_to_en() -> None:
    assert locale_from_accept_language(None, "fr") == "en"
    assert locale_from_accept_language(None, None) == "en"


def test_allowed_web_origins_use_web_origin_and_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:4200, https://app.procurepilot.test/")
    monkeypatch.setenv("WEB_ORIGIN", "https://www.procurepilot.test")
    monkeypatch.setenv("WEB_PUBLIC_URL", "https://public.procurepilot.test/some/path")
    settings = Settings()
    origins = allowed_web_origins(settings)
    assert origins == (
        "https://www.procurepilot.test",
        "https://public.procurepilot.test",
        "http://localhost:4200",
        "https://app.procurepilot.test",
    )
