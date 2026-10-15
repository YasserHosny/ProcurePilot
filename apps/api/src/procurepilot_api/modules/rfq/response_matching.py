from __future__ import annotations

from typing import TypedDict
from uuid import UUID


class OpenRfqRecipientRow(TypedDict):
    id: UUID
    outbound_message_id: str
    rfq_id: UUID
    supplier_id: UUID


def _normalize_message_id(message_id: str | None) -> str | None:
    if not message_id:
        return None
    return message_id.strip().strip("<>") or None


def match_rfq_response(
    *,
    in_reply_to: str | None,
    references: list[str],
    open_recipients: list[OpenRfqRecipientRow],
) -> UUID | None:
    """Prefer a direct parent, then the newest same-supplier reference; ambiguity returns None.

    Cross-supplier ambiguity falls back to cascade/review without creating an rfq_response.
    """
    direct_parent = _normalize_message_id(in_reply_to)
    recipients_by_message_id: dict[str, list[OpenRfqRecipientRow]] = {}
    for recipient in open_recipients:
        outbound_id = _normalize_message_id(recipient["outbound_message_id"])
        if outbound_id:
            recipients_by_message_id.setdefault(outbound_id, []).append(recipient)

    if direct_parent:
        direct_matches = recipients_by_message_id.get(direct_parent, [])
        if direct_matches:
            suppliers = {recipient["supplier_id"] for recipient in direct_matches}
            if len(suppliers) > 1:
                return None
            return min(direct_matches, key=lambda recipient: str(recipient["id"]))["id"]

    reference_matches: list[tuple[int, OpenRfqRecipientRow]] = []
    for index, reference in enumerate(references):
        normalized_reference = _normalize_message_id(reference)
        if normalized_reference:
            reference_matches.extend(
                (index, recipient)
                for recipient in recipients_by_message_id.get(normalized_reference, [])
            )

    if not reference_matches:
        return None
    if len({recipient["supplier_id"] for _, recipient in reference_matches}) > 1:
        return None

    latest_index = max(index for index, _ in reference_matches)
    latest_matches = [recipient for index, recipient in reference_matches if index == latest_index]
    return min(latest_matches, key=lambda recipient: str(recipient["id"]))["id"]
