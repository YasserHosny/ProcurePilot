from __future__ import annotations

import email
import email.policy
from dataclasses import dataclass, field

import magic

# T010 (research R2): stdlib `email` for MIME parsing, `python-magic` for content-type
# sniffing independent of the declared header. No other new dependency.


@dataclass(frozen=True)
class ParsedAttachment:
    filename: str
    declared_content_type: str
    detected_content_type: str
    size_bytes: int
    content: bytes

    @property
    def content_type_mismatch(self) -> bool:
        """R2: reject attachments where the sniffed type disagrees with the declared one — the
        defence against a disguised executable wearing a PDF's Content-Type header. Compares
        only the top-level media type (application/pdf vs application/octet-stream would flag;
        text/csv vs text/plain, both genuinely textual, would not) since mail clients are
        inconsistent about the exact declared subtype for the same real content."""
        declared_major = self.declared_content_type.split("/")[0].lower()
        detected_major = self.detected_content_type.split("/")[0].lower()
        return declared_major != detected_major


@dataclass(frozen=True)
class InboundEmail:
    message_id: str
    from_address: str
    from_domain: str
    subject: str | None
    in_reply_to: str | None
    references: list[str] = field(default_factory=list)
    body_text: str | None = None
    attachments: list[ParsedAttachment] = field(default_factory=list)


class EmailParseError(ValueError):
    pass


def parse_email(raw_bytes: bytes) -> InboundEmail:
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    message_id = _clean_message_id(msg.get("Message-ID"))
    if not message_id:
        raise EmailParseError("missing_message_id")

    from_header = msg.get("From")
    from_address = _extract_address(from_header)
    if not from_address:
        raise EmailParseError("missing_from_address")
    from_domain = from_address.rsplit("@", 1)[-1].lower()

    in_reply_to = _clean_message_id(msg.get("In-Reply-To"))
    references = [
        ref for ref in (_clean_message_id(r) for r in _split_references(msg.get("References")))
        if ref
    ]

    body_text = _extract_body_text(msg)
    attachments = _extract_attachments(msg)

    return InboundEmail(
        message_id=message_id,
        from_address=from_address.lower(),
        from_domain=from_domain,
        subject=msg.get("Subject"),
        in_reply_to=in_reply_to,
        references=references,
        body_text=body_text,
        attachments=attachments,
    )


def _clean_message_id(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().strip("<>") or None


def _split_references(raw: str | None) -> list[str]:
    if not raw:
        return []
    return raw.split()


def _extract_address(from_header: str | None) -> str | None:
    if not from_header:
        return None
    _, address = email.utils.parseaddr(from_header)
    return address or None


def _extract_body_text(msg: email.message.EmailMessage) -> str | None:
    body = msg.get_body(preferencelist=("plain",))
    if body is None:
        return None
    try:
        return str(body.get_content()).strip() or None
    except Exception:
        return None


def _extract_attachments(msg: email.message.EmailMessage) -> list[ParsedAttachment]:
    attachments: list[ParsedAttachment] = []
    for part in msg.iter_attachments():
        content = part.get_content()
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not isinstance(content, (bytes, bytearray)):
            continue
        content = bytes(content)
        filename = part.get_filename() or "attachment"
        declared = part.get_content_type()
        detected = magic.from_buffer(content, mime=True)
        attachments.append(
            ParsedAttachment(
                filename=filename,
                declared_content_type=declared,
                detected_content_type=detected,
                size_bytes=len(content),
                content=content,
            )
        )
    return attachments
