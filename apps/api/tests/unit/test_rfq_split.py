from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.offers.rfq_split import build_rfq_split_request


@pytest.fixture
def member() -> CurrentMember:
    return CurrentMember(
        tenant_id=uuid4(),
        user_id=uuid4(),
        membership_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def _reply(**changes: object) -> dict[str, object]:
    return {
        "quotation_id": uuid4(),
        "response_id": uuid4(),
        "supplier_id": uuid4(),
        "status": "reviewed",
        "deleted_at": None,
        "line_count": 4,
        "unmatched_count": 0,
        "currencies": ["SAR"],
        **changes,
    }


def _connection(replies: list[dict[str, object]], *, status: str = "responded") -> MagicMock:
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = {"status": status}
    cur.fetchall.side_effect = [
        replies,
        [
            {
                "workspace_product_id": uuid4(),
                "quantity": Decimal("25"),
                "base_quantity": Decimal("10"),
            },
            {
                "workspace_product_id": uuid4(),
                "quantity": Decimal("6"),
                "base_quantity": Decimal("18"),
            },
        ],
    ]
    return conn


def test_build_converts_packs_and_snapshots_only_eligible_replies(member: CurrentMember) -> None:
    replies = [_reply(), _reply()]
    excluded = [_reply(status="refused"), _reply(status="pending"), _reply(deleted_at="yesterday")]
    rfq_id = uuid4()
    payload, snapshot = build_rfq_split_request(_connection(replies + excluded), member, rfq_id)
    assert [Decimal(item.quantity) for item in payload.items] == [Decimal(250), Decimal(108)]
    assert payload.supplier_ids == [reply["supplier_id"] for reply in replies]
    assert snapshot["rfq_id"] == str(rfq_id)
    assert snapshot["price_quotation_ids"] == [str(reply["quotation_id"]) for reply in replies]
    assert snapshot["rfq_response_ids"] == [str(reply["response_id"]) for reply in replies]
    assert list(map(Decimal, snapshot["pack_base_quantities"].values())) == [
        Decimal(10),
        Decimal(18),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"unmatched_count": 1},
        {"status": "pending"},
        {"status": "refused"},
        {"deleted_at": "yesterday"},
        {"line_count": 0},
    ],
)
def test_not_enough_eligible_replies(member: CurrentMember, bad: dict[str, object]) -> None:
    reply = _reply(**bad)
    with pytest.raises(ConflictError) as caught:
        build_rfq_split_request(_connection([_reply(), reply]), member, uuid4())
    assert caught.value.details == {
        "reason": "not_enough_replies",
        "eligible": 1,
        "unmatched_quotation_ids": [str(reply["quotation_id"])]
        if bad.get("unmatched_count")
        else [],
    }


def test_unmatched_reply_is_excluded_with_two_eligible_replies(member: CurrentMember) -> None:
    replies = [_reply(), _reply()]
    excluded = _reply(unmatched_count=1, currencies=["USD"])
    payload, snapshot = build_rfq_split_request(_connection([*replies, excluded]), member, uuid4())
    assert payload.supplier_ids == [reply["supplier_id"] for reply in replies]
    assert snapshot["price_quotation_ids"] == [str(reply["quotation_id"]) for reply in replies]
    assert snapshot["rfq_response_ids"] == [str(reply["response_id"]) for reply in replies]


def test_mixed_currency(member: CurrentMember) -> None:
    with pytest.raises(ConflictError) as caught:
        build_rfq_split_request(
            _connection([_reply(), _reply(currencies=["USD"])]), member, uuid4()
        )
    assert caught.value.details["reason"] == "mixed_currency"


def test_converted_rfq(member: CurrentMember) -> None:
    with pytest.raises(ConflictError) as caught:
        build_rfq_split_request(_connection([], status="converted"), member, uuid4())
    assert caught.value.details["reason"] == "rfq_already_converted"
