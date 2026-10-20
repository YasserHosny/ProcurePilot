from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.scoring import SCORING_VERSION
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.modules.quotations import confirmation_service as confirmation_module
from procurepilot_api.modules.quotations.confirmation_service import QuotationConfirmationService


class _ConfirmationQuery:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.updates: dict[str, object] | None = None

    def table(self, _name: str) -> _ConfirmationQuery:
        return self

    def select(self, _columns: str) -> _ConfirmationQuery:
        return self

    def eq(self, _column: str, _value: object) -> _ConfirmationQuery:
        return self

    def limit(self, _limit: int) -> _ConfirmationQuery:
        return self

    def in_(self, _column: str, _values: list[str]) -> _ConfirmationQuery:
        return self

    def is_(self, _column: str, _value: object) -> _ConfirmationQuery:
        return self

    def lt(self, _column: str, _value: object) -> _ConfirmationQuery:
        return self

    def update(self, values: dict[str, object]) -> _ConfirmationQuery:
        self.updates = values
        return self

    def execute(self) -> SimpleNamespace:
        if self.updates and self.updates.get("status") == "reviewed":
            self.row.update(self.updates)
        self.updates = None
        return SimpleNamespace(data=[self.row.copy()])


def _member() -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )


def test_quotation_confirm_matching_exception_preserves_authorisation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quotation_id = uuid4()
    member = _member()
    row: dict[str, object] = {
        "id": quotation_id,
        "status": "extracted",
        "supplier_id": uuid4(),
        "currency": "GBP",
    }
    query = _ConfirmationQuery(row)
    monkeypatch.setattr(confirmation_module, "authenticated_client", lambda *_args: query)
    monkeypatch.setattr(confirmation_module, "blocking_low_confidence_fields", lambda *_a, **_k: [])
    monkeypatch.setattr(confirmation_module, "_quotation", lambda result: result)
    monkeypatch.setattr(
        confirmation_module,
        "get_audit_writer",
        lambda: SimpleNamespace(record=lambda *_a, **_k: None),
    )
    calls = []

    def prepare(_self: object, **kwargs: object) -> None:
        assert row["status"] == "reviewed"
        assert kwargs == {
            "bearer_token": "caller-token",
            "member": member,
            "quotation_id": quotation_id,
        }
        calls.append(kwargs)
        raise RuntimeError("preparation unavailable")

    monkeypatch.setattr(MatchingService, "quotation_matches", prepare)
    result = QuotationConfirmationService().confirm(
        bearer_token="caller-token",
        member=member,
        quotation_id=quotation_id,
        payload=None,
    )
    assert result["status"] == row["status"] == "reviewed"
    assert len(calls) == 1
    assert "Failed to prepare matching" in caplog.text


class _ConflictingInsert:
    def table(self, _name: str) -> _ConflictingInsert:
        return self

    def insert(self, _values: dict[str, object]) -> _ConflictingInsert:
        return self

    def execute(self) -> None:
        raise APIError({"code": "23505", "message": "concurrent insert"})


@pytest.mark.parametrize("record", ["candidate", "decision", "task"])
def test_matching_concurrent_preparation_reuses_unique_constraint_winner(
    record: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MatchingService(get_settings())
    client = _ConflictingInsert()
    member = _member()
    line = {"id": uuid4(), "quotation_id": uuid4()}
    product_id = uuid4()
    candidate = {
        "id": uuid4(),
        "candidate_workspace_product_id": product_id,
        "scoring_version": SCORING_VERSION,
        "confidence": "1",
        "reasons": {},
    }
    existing = {"id": uuid4()}
    monkeypatch.setattr(matching_module, "_candidate_rows", lambda *_a: [candidate])
    monkeypatch.setattr(matching_module, "_decision_for_line", lambda *_a: existing)
    # First task check sees nothing; the second sees the concurrent winner.
    tasks = iter([None, existing])
    monkeypatch.setattr(matching_module, "_open_task_for_line", lambda *_a: next(tasks))
    if record == "candidate":
        result = service._persist_candidates(  # noqa: SLF001
            client,
            member,
            line,
            [{"workspace_product_id": product_id, "confidence": "1", "reasons": {}}],
        )
        assert result == [candidate]
    elif record == "decision":
        assert (
            service._create_automatic_decision(  # noqa: SLF001
                client,
                member,
                line,
                candidate,
            )
            == existing
        )
    else:
        service._create_task(client, member, line, reason="no_candidate")  # noqa: SLF001
        assert next(tasks, "exhausted") == "exhausted"
