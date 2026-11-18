"""Operator feedback status machine and label rules (spec 025, FR-018 / research D7).

The database trigger is the authority; the API pre-checks the same table so it can answer 409
`feedback.invalid_transition` before it touches a row. These run without a database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.feedback.operator_schemas import (
    FeedbackStatus,
    OperatorUpdateRequest,
)
from procurepilot_api.modules.feedback.operator_service import (
    FeedbackInvalidTransitionError,
    assert_valid_transition,
    is_valid_transition,
)

N, R, D = FeedbackStatus.new, FeedbackStatus.reviewed, FeedbackStatus.resolved


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (N, R, True),
        (N, D, True),
        (R, D, True),
        # Same status is a no-op (a labels-only change repeats the current status).
        (N, N, True),
        (R, R, True),
        (D, D, True),
        # Never backwards: moving back to `new` would reopen withdrawal.
        (R, N, False),
        (D, N, False),
        (D, R, False),
    ],
)
def test_transition_table(current: FeedbackStatus, target: FeedbackStatus, allowed: bool) -> None:
    assert is_valid_transition(current, target) is allowed


def test_assert_valid_transition_raises_the_documented_code() -> None:
    with pytest.raises(FeedbackInvalidTransitionError) as raised:
        assert_valid_transition(D, N)
    assert raised.value.code == "feedback.invalid_transition"
    assert raised.value.status_code == 409
    assert raised.value.details == {"from": "resolved", "to": "new"}


def test_assert_valid_transition_accepts_forward_moves() -> None:
    assert_valid_transition(N, R)
    assert_valid_transition(R, D)


def test_update_request_requires_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        OperatorUpdateRequest()


def test_update_request_accepts_status_only_and_labels_only() -> None:
    assert OperatorUpdateRequest(status=FeedbackStatus.reviewed).labels is None
    assert OperatorUpdateRequest(labels=[]).labels == []


def test_labels_are_trimmed_and_deduplicated_in_order() -> None:
    request = OperatorUpdateRequest(labels=["  billing ", "ui", "billing"])
    assert request.labels == ["billing", "ui"]


@pytest.mark.parametrize("bad", [[""], ["   "], ["x" * 41]])
def test_label_length_is_one_to_forty(bad: list[str]) -> None:
    with pytest.raises(ValidationError):
        OperatorUpdateRequest(labels=bad)


def test_label_boundaries_are_accepted() -> None:
    assert OperatorUpdateRequest(labels=["x", "y" * 40]).labels == ["x", "y" * 40]


def test_at_most_ten_labels() -> None:
    assert len(OperatorUpdateRequest(labels=[f"l{i}" for i in range(10)]).labels or []) == 10
    with pytest.raises(ValidationError):
        OperatorUpdateRequest(labels=[f"l{i}" for i in range(11)])
