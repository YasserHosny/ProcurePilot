"""Operator feedback digest renderer (spec 025 T061, FR-024). No database needed."""

from __future__ import annotations

from datetime import UTC, datetime

from procurepilot_api.modules.feedback.digest_renderer import (
    MAX_ITEMS,
    DigestItem,
    render_feedback_digest,
)

WHEN = datetime(2026, 11, 18, 7, 30, tzinfo=UTC)
BASE = "https://app.example.test"


def _item(**overrides: object) -> DigestItem:
    values: dict[str, object] = {
        "workspace_name": "Sanad Restaurants",
        "category": "bug",
        "text": "The compare page is slow",
        "created_at": WHEN,
    }
    values.update(overrides)
    return DigestItem(**values)  # type: ignore[arg-type]


def test_english_digest_has_workspace_category_excerpt_and_link() -> None:
    subject, html_body, text_body = render_feedback_digest([_item()], "en", BASE)
    assert "1" in subject
    for body in (html_body, text_body):
        assert "Sanad Restaurants" in body
        assert "The compare page is slow" in body
        assert "Bug" in body
        assert f"{BASE}/platform/feedback" in body
    assert 'lang="en"' in html_body and 'dir="ltr"' in html_body


def test_arabic_digest_is_rtl_and_translated() -> None:
    subject, html_body, text_body = render_feedback_digest(
        [_item(workspace_name="مطاعم سند", category="idea", text="أضيفوا تصدير")], "ar", BASE
    )
    assert 'lang="ar"' in html_body and 'dir="rtl"' in html_body
    assert "مطاعم سند" in html_body and "مطاعم سند" in text_body
    # No untranslated key leaks through t()'s raw-key fallback.
    for body in (subject, html_body, text_body):
        assert "emails.feedbackDigest" not in body
    assert "فكرة" in text_body


def test_excerpt_is_truncated_and_whitespace_collapsed() -> None:
    long_text = "word " * 200
    _, html_body, text_body = render_feedback_digest([_item(text=long_text)], "en", BASE)
    assert "word " * 200 not in text_body
    assert "…" in text_body
    assert "\n\n\n" not in text_body
    assert "…" in html_body


def test_html_is_escaped() -> None:
    _, html_body, _ = render_feedback_digest(
        [_item(text="<script>alert(1)</script>", workspace_name="A & B <i>")], "en", BASE
    )
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
    assert "A &amp; B &lt;i&gt;" in html_body


def test_email_addresses_typed_by_submitters_never_reach_the_digest() -> None:
    for locale in ("en", "ar"):
        subject, html_body, text_body = render_feedback_digest(
            [_item(text="please call me, mail sara.k@example.com thanks")], locale, BASE
        )
        for body in (subject, html_body, text_body):
            assert "sara.k@example.com" not in body
            assert "@example.com" not in body


def test_missing_category_uses_the_localised_fallback() -> None:
    _, _, text_body = render_feedback_digest([_item(category=None)], "en", BASE)
    assert "No category" in text_body


def test_overflow_is_summarised_not_listed() -> None:
    items = [_item(text=f"item {n}") for n in range(MAX_ITEMS + 5)]
    subject, _, text_body = render_feedback_digest(items, "en", BASE)
    assert str(MAX_ITEMS + 5) in subject
    assert f"item {MAX_ITEMS - 1}" in text_body
    assert f"item {MAX_ITEMS}" not in text_body
    assert "5 more" in text_body


def test_trailing_slash_in_base_url_is_tolerated() -> None:
    _, _, text_body = render_feedback_digest([_item()], "en", BASE + "/")
    assert f"{BASE}/platform/feedback" in text_body
    assert f"{BASE}//platform" not in text_body


def test_digest_never_carries_attachment_references() -> None:
    _, html_body, text_body = render_feedback_digest([_item()], "en", BASE)
    for body in (html_body, text_body):
        assert "storage" not in body.lower()
        assert "attachment" not in body.lower()
