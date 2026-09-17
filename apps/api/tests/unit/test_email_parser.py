from __future__ import annotations

from email.message import EmailMessage

import pytest

from procurepilot_api.modules.ingestion.email_parser import EmailParseError, parse_email


def _build_email(
    *,
    from_addr: str = "sales@acme.com",
    message_id: str = "<abc123@acme.com>",
    in_reply_to: str | None = None,
    references: str | None = None,
    subject: str = "Quotation",
    body: str = "Please find our quotation attached.",
    html_body: str | None = None,
    body_charset: str | None = None,
    attachments: list[tuple[bytes, str, str, str]] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = "buyer@ingest.procurepilot.local"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    if body_charset:
        msg.set_content(body, subtype="plain", charset=body_charset)
    else:
        msg.set_content(body, subtype="plain")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for content, maintype, subtype, filename in attachments or []:
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes()


def test_parses_from_address_subject_and_body() -> None:
    raw = _build_email(from_addr="Sales Team <sales@acme.com>", subject="June Quote")
    result = parse_email(raw)

    assert result.from_address == "sales@acme.com"
    assert result.from_domain == "acme.com"
    assert result.subject == "June Quote"
    assert result.message_id == "abc123@acme.com"
    assert result.body_text == "Please find our quotation attached."
    assert result.attachments == []


def test_parses_thread_headers() -> None:
    raw = _build_email(
        in_reply_to="<prev@acme.com>",
        references="<prev@acme.com> <prev2@acme.com>",
    )
    result = parse_email(raw)

    assert result.in_reply_to == "prev@acme.com"
    assert result.references == ["prev@acme.com", "prev2@acme.com"]


def test_parses_a_single_attachment() -> None:
    raw = _build_email(
        attachments=[(b"%PDF-1.4 fake pdf content", "application", "pdf", "quote.pdf")]
    )
    result = parse_email(raw)

    assert len(result.attachments) == 1
    attachment = result.attachments[0]
    assert attachment.filename == "quote.pdf"
    assert attachment.declared_content_type == "application/pdf"
    assert attachment.detected_content_type == "application/pdf"
    assert not attachment.content_type_mismatch


def test_parses_multiple_attachments_as_separate_records() -> None:
    raw = _build_email(
        attachments=[
            (b"%PDF-1.4 fake pdf content", "application", "pdf", "quote.pdf"),
            (b"col1,col2\n1,2\n", "text", "csv", "prices.csv"),
        ]
    )
    result = parse_email(raw)

    assert [a.filename for a in result.attachments] == ["quote.pdf", "prices.csv"]


def test_flags_content_type_mismatch_for_disguised_content() -> None:
    # Declared as a PDF, but the actual bytes are a script — python-magic sniffs the real type.
    raw = _build_email(
        attachments=[(b"#!/bin/sh\necho pwned\n", "application", "pdf", "quote.pdf")]
    )
    result = parse_email(raw)

    assert result.attachments[0].content_type_mismatch


def test_missing_message_id_raises_parse_error() -> None:
    msg = EmailMessage()
    msg["From"] = "sales@acme.com"
    msg["Subject"] = "No message id"
    msg.set_content("body")
    raw = msg.as_bytes()

    with pytest.raises(EmailParseError):
        parse_email(raw)


def test_missing_from_address_raises_parse_error() -> None:
    msg = EmailMessage()
    msg["Message-ID"] = "<abc@acme.com>"
    msg["Subject"] = "No sender"
    msg.set_content("body")
    raw = msg.as_bytes()

    with pytest.raises(EmailParseError):
        parse_email(raw)


def test_parses_body_only_email_with_zero_attachments() -> None:
    raw = _build_email(
        body="Plain text inquiry with no files attached.",
        attachments=[],
    )
    result = parse_email(raw)

    assert result.attachments == []
    assert result.body_text == "Plain text inquiry with no files attached."


def test_parses_multipart_alternative_prefers_plain_text_over_html() -> None:
    plain_text = "Please review our quotation for the requested industrial valves."
    html_text = "<p>Please review our <b>quotation</b> for the requested industrial valves.</p>"
    raw = _build_email(body=plain_text, html_body=html_text)
    result = parse_email(raw)

    assert result.body_text == plain_text
    assert "<p>" not in (result.body_text or "")
    assert "<b>" not in (result.body_text or "")
    assert result.attachments == []


def test_parses_non_ascii_rfc2047_subject_and_non_utf8_charset_body() -> None:
    arabic_subject = "طلب تسعير مواد ومعدات"
    arabic_body = "يرجى تزويدنا بعروض الأسعار الخاصة بالمعدات المطلوبة."
    raw = _build_email(
        subject=arabic_subject,
        body=arabic_body,
        body_charset="windows-1256",
    )

    # Verify that the raw email encoded subject with RFC 2047 and body with windows-1256
    assert b"=?utf-8?" in raw.lower()
    assert b"windows-1256" in raw.lower()

    result = parse_email(raw)

    assert result.subject == arabic_subject
    assert result.body_text == arabic_body


def test_malformed_garbage_bytes_raise_email_parse_error() -> None:
    raw = b"not an email at all, just noise"

    with pytest.raises(EmailParseError):
        parse_email(raw)

