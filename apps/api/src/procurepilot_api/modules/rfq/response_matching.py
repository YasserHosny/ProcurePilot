from __future__ import annotations

from typing import TypedDict
from uuid import UUID


class OpenRfqRecipientRow(TypedDict):
    id: UUID
    outbound_message_id: str
    rfq_id: UUID
    supplier_id: UUID

def match_rfq_response(
    *,
    in_reply_to: str | None,
    references: list[str],
    open_recipients: list[OpenRfqRecipientRow],
) -> UUID | None:
    """
    Pure function to match an inbound email's thread headers against a tenant's open RFQ recipients.
    Returns the ID of the matched rfq_recipient, or None if no match is found.
    """
    thread_ids = {m for m in [in_reply_to, *references] if m}
    if not thread_ids:
        return None
        
    for recipient in open_recipients:
        outbound_msg_id = recipient["outbound_message_id"]
        if outbound_msg_id:
            cleaned_outbound = outbound_msg_id.strip("<>")
            if cleaned_outbound in thread_ids:
                return recipient["id"]
            
    return None
