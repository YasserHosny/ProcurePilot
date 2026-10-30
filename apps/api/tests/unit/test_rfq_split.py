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


def test_two_reviewed_replies_from_same_supplier_plus_one_from_another(
    member: CurrentMember,
) -> None:
    supplier1 = uuid4()
    supplier2 = uuid4()
    reply1a = _reply(supplier_id=supplier1)
    reply1b = _reply(supplier_id=supplier1)
    reply2 = _reply(supplier_id=supplier2)
    payload, snapshot = build_rfq_split_request(
        _connection([reply1a, reply1b, reply2]), member, uuid4()
    )
    assert payload.supplier_ids == [supplier1, supplier2]
    assert snapshot["price_quotation_ids"] == [
        str(reply1a["quotation_id"]),
        str(reply1b["quotation_id"]),
        str(reply2["quotation_id"]),
    ]


def test_two_replies_from_one_supplier_only(member: CurrentMember) -> None:
    supplier = uuid4()
    reply1 = _reply(supplier_id=supplier)
    reply2 = _reply(supplier_id=supplier)
    with pytest.raises(ConflictError) as caught:
        build_rfq_split_request(_connection([reply1, reply2]), member, uuid4())
    assert caught.value.details == {
        "reason": "not_enough_replies",
        "eligible": 1,
        "unmatched_quotation_ids": [],
    }


@pytest.mark.parametrize(
    "change", ["new_reply", "ineligible_reply", "new_cost", "missing_cost", "unchanged"]
)
def test_preparation_staleness(change: str) -> None:
    from procurepilot_api.modules.offers.rfq_split import split_is_stale

    quotations = [str(uuid4()), str(uuid4())]
    costs = [str(uuid4()), str(uuid4())]
    current_quotations = list(quotations)
    current_costs = list(costs)
    if change == "new_reply":
        current_quotations.append(str(uuid4()))
    elif change == "ineligible_reply":
        current_quotations.pop()
    elif change == "new_cost":
        current_costs[0] = str(uuid4())
    elif change == "missing_cost":
        current_costs[0] = None
    assert split_is_stale(quotations, costs, current_quotations, current_costs) == (
        change != "unchanged"
    )


@pytest.mark.parametrize(
    "base,expected",
    [
        ("250", 25),
        ("250.00001", 25),
        ("249.99999", 25),
        ("250.000011", None),
        ("249.999989", None),
        ("255", None),
    ],
)
def test_base_to_whole_packs_tolerance(base: str, expected: int | None) -> None:
    from procurepilot_api.modules.offers.rfq_split import base_to_packs

    if expected is None:
        with pytest.raises(ConflictError) as caught:
            base_to_packs(Decimal(base), Decimal(10))
        assert caught.value.details["reason"] == "allocation_not_whole_packs"
    else:
        assert base_to_packs(Decimal(base), Decimal(10)) == Decimal(expected)
