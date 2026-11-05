"""P-154: who decided, and the correction chain of a line (ADR-022 keeps every decision)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.matching import service as svc
from procurepilot_api.modules.matching.schemas import ProductSummary
from procurepilot_api.modules.matching.service import MatchingService

LINE = uuid4()
BASE = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def _product() -> ProductSummary:
    return ProductSummary(
        id=uuid4(), tenant_name="Oil 5L", canonical_name="Oil", base_unit="L", status="active"
    )


def _row(
    *,
    minutes: int,
    decided_by: UUID | None,
    automatic: bool,
    supersedes: UUID | None = None,
    outcome: str = "same_product",
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "quotation_line_id": str(LINE),
        "matched_workspace_product_id": str(uuid4()),
        "selected_match_candidate_id": None,
        "outcome": outcome,
        "is_automatic": automatic,
        "decided_by": str(decided_by) if decided_by else None,
        "decided_at": (BASE + timedelta(minutes=minutes)).isoformat(),
        "confidence": "0.9000",
        "alias_id": None,
        "supersedes_decision_id": str(supersedes) if supersedes else None,
        "learned_from_decision_id": None,
    }


def _service(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> MatchingService:
    client = MagicMock()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value
    chain.order.return_value.execute.return_value.data = rows
    chain.execute.return_value.data = rows
    monkeypatch.setattr(svc, "authenticated_client", lambda *_: client)
    monkeypatch.setattr(svc, "_line_row", lambda *_: {"id": str(LINE)})
    monkeypatch.setattr(svc, "_product_summary", lambda *_: _product())
    emails = {}
    monkeypatch.setattr(svc, "_membership_email", lambda _c, mid: emails.get(str(mid)))
    service = MatchingService.__new__(MatchingService)
    service._settings = MagicMock()
    service._emails = emails  # type: ignore[attr-defined]
    return service


def test_history_lists_the_chain_oldest_first_with_who_decided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer = uuid4()
    first = _row(minutes=0, decided_by=None, automatic=True)
    second = _row(
        minutes=5,
        decided_by=buyer,
        automatic=False,
        supersedes=UUID(str(first["id"])),
    )
    service = _service(monkeypatch, [first, second])
    service._emails[str(buyer)] = "buyer@example.test"  # type: ignore[attr-defined]
    result = service.decision_history(bearer_token="t", line_id=LINE)
    assert [d.id for d in result.items] == [UUID(str(first["id"])), UUID(str(second["id"]))]
    assert result.items[0].is_automatic is True
    assert result.items[0].decided_by_email is None
    assert result.items[1].decided_by_email == "buyer@example.test"
    assert result.items[1].supersedes_decision_id == UUID(str(first["id"]))


def test_history_of_a_line_with_no_decision_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _service(monkeypatch, []).decision_history(bearer_token="t", line_id=LINE).items == []


def test_history_of_an_unreadable_line_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch, [])

    def missing(*_: object) -> dict[str, object]:
        raise NotFoundError(details={"resource": "quotation_line"})

    monkeypatch.setattr(svc, "_line_row", missing)
    with pytest.raises(NotFoundError):
        service.decision_history(bearer_token="t", line_id=LINE)


def test_the_decision_on_a_task_carries_who_decided(monkeypatch: pytest.MonkeyPatch) -> None:
    buyer = uuid4()
    monkeypatch.setattr(svc, "_membership_email", lambda _c, _m: "buyer@example.test")
    row = _row(minutes=0, decided_by=buyer, automatic=False)
    monkeypatch.setattr(svc, "_product_summary", lambda *_: _product())
    decision = svc._decision_with_actor(MagicMock(), row)
    assert decision.decided_by_email == "buyer@example.test"
    automatic = svc._decision_with_actor(
        MagicMock(), _row(minutes=0, decided_by=None, automatic=True)
    )
    assert automatic.decided_by_email is None
