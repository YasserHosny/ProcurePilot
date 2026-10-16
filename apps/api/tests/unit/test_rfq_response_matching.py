from __future__ import annotations

from uuid import UUID, uuid4

from procurepilot_api.modules.rfq.response_matching import (
    OpenRfqRecipientRow,
    match_rfq_response,
)


def _recipient(
    message_id: str, supplier_id: UUID, recipient_id: UUID | None = None
) -> OpenRfqRecipientRow:
    return {
        "id": recipient_id or uuid4(),
        "outbound_message_id": message_id,
        "rfq_id": uuid4(),
        "supplier_id": supplier_id,
    }


def test_references_across_suppliers_are_ambiguous() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    recipients = [
        _recipient("a@example.test", supplier_a),
        _recipient("b@example.test", supplier_b),
    ]

    result = match_rfq_response(
        in_reply_to="unmatched@example.test",
        references=["a@example.test", "b@example.test"],
        open_recipients=recipients,
    )

    assert result is None


def test_direct_parent_wins_over_reference_from_another_supplier() -> None:
    supplier_a, supplier_b = uuid4(), uuid4()
    direct, other = (
        _recipient("direct@example.test", supplier_a),
        _recipient("other@example.test", supplier_b),
    )

    result = match_rfq_response(
        in_reply_to="direct@example.test",
        references=["other@example.test"],
        open_recipients=[other, direct],
    )

    assert result == direct["id"]


def test_same_supplier_references_choose_latest_reference() -> None:
    supplier = uuid4()
    older, newer = (
        _recipient("older@example.test", supplier),
        _recipient("newer@example.test", supplier),
    )

    result = match_rfq_response(
        in_reply_to=None,
        references=["older@example.test", "newer@example.test"],
        open_recipients=[newer, older],
    )

    assert result == newer["id"]


def test_header_and_outbound_ids_are_normalized() -> None:
    recipient = _recipient("  <id@example.test>  ", uuid4())

    result = match_rfq_response(
        in_reply_to="  <id@example.test>  ",
        references=[],
        open_recipients=[recipient],
    )

    assert result == recipient["id"]


def test_direct_parent_duplicate_across_suppliers_is_ambiguous() -> None:
    message_id = "same@example.test"
    recipients = [_recipient(message_id, uuid4()), _recipient(message_id, uuid4())]

    result = match_rfq_response(
        in_reply_to=message_id,
        references=[],
        open_recipients=recipients,
    )

    assert result is None


def test_no_headers_returns_none() -> None:
    result = match_rfq_response(in_reply_to=None, references=[], open_recipients=[])

    assert result is None


def test_direct_parent_same_supplier_duplicate_uses_recipient_id_tie_break() -> None:
    supplier = uuid4()
    recipient_a = _recipient("same@example.test", supplier, UUID(int=2))
    recipient_b = _recipient("same@example.test", supplier, UUID(int=1))

    result = match_rfq_response(
        in_reply_to="same@example.test",
        references=[],
        open_recipients=[recipient_a, recipient_b],
    )

    assert result == recipient_b["id"]
