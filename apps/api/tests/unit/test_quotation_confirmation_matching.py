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


@pytest.fixture(autouse=True)
def _no_rfq_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matching_module, "rfq_lines_for_quotation", lambda *_: None)


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

    def insert(self, _values: dict[str, object] | list[dict[str, object]]) -> _ConflictingInsert:
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
    line = {"id": uuid4(), "quotation_id": uuid4(), "line_number": 1}
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


def test_matching_preparation_never_routes_a_partial_candidate_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "matching_fuzzy_auto_accept_enabled": True,
            "matching_auto_accept_threshold": 0.92,
            "matching_review_margin": 0.05,
        }
    )
    service = MatchingService(settings)
    member = _member()
    line = {"id": uuid4(), "quotation_id": uuid4(), "line_number": 1}
    candidates = [
        {"workspace_product_id": uuid4(), "confidence": "0.98", "reasons": {}},
        {"workspace_product_id": uuid4(), "confidence": "0.97", "reasons": {}},
    ]
    visible: list[dict[str, object]] = []
    decisions: list[object] = []
    task_reasons: list[object] = []
    observations: list[int] = []

    class InterleavedInsert:
        def __init__(self) -> None:
            self.rows: list[dict[str, object]] = []

        def table(self, name: str) -> InterleavedInsert:
            assert name == "match_candidate"
            return self

        def insert(self, payload: dict[str, object] | list[dict[str, object]]) -> InterleavedInsert:
            self.rows = payload if isinstance(payload, list) else [payload]
            return self

        def execute(self) -> SimpleNamespace:
            # PostgREST commits one insert statement, then the competing GET runs.
            # The old implementation exposes rank 1 alone at this exact boundary.
            existing_products = {row["candidate_workspace_product_id"] for row in visible}
            if any(row["candidate_workspace_product_id"] in existing_products for row in self.rows):
                raise APIError({"code": "23505", "message": "concurrent insert"})
            committed = [{"id": uuid4(), **row} for row in self.rows]
            visible.extend(committed)
            observations.append(len(visible))
            service._ensure_pipeline(  # noqa: SLF001
                client=self, member=member, quote={"id": line["quotation_id"]}, lines=[line]
            )
            return SimpleNamespace(data=list(reversed(committed)))

    monkeypatch.setattr(service, "_backfill_missing_embeddings", lambda _client: None)
    monkeypatch.setattr(matching_module, "_decision_for_line", lambda *_a: None)
    monkeypatch.setattr(matching_module, "_candidate_rows", lambda *_a: list(visible))
    monkeypatch.setattr(
        service, "_create_automatic_decision", lambda *_a, **_k: decisions.append(True)
    )
    monkeypatch.setattr(
        service, "_create_task", lambda *_a, **kwargs: task_reasons.append(kwargs["reason"])
    )
    client = InterleavedInsert()
    persisted = service._persist_candidates(client, member, line, candidates)  # noqa: SLF001
    service._route_or_accept(client, member, line, persisted)  # noqa: SLF001
    assert decisions == []
    assert observations == [2]
    assert [row["rank"] for row in persisted] == [1, 2]
    assert task_reasons == ["close_candidates", "close_candidates"]

    # A losing runner with a different computed set must route the winner's entire
    # committed set, rather than just reusing its own overlapping candidate.
    reused = service._persist_candidates(client, member, line, candidates[:1])  # noqa: SLF001
    assert reused == visible
    service._route_or_accept(client, member, line, reused)  # noqa: SLF001
    assert decisions == []
    assert task_reasons[-1] == "close_candidates"


@pytest.mark.parametrize("deterministic_top", [True, False])
def test_matching_deterministic_preparation_preserves_below_threshold_auto_accept(
    deterministic_top: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MatchingService(
        get_settings().model_copy(update={"matching_auto_accept_threshold": 0.92})
    )
    member = _member()
    line = {"id": uuid4(), "quotation_id": uuid4(), "line_number": 1}
    deterministic = SimpleNamespace(
        workspace_product_id=uuid4(), confidence="0.80", reasons={"alias_hit": True}
    )
    persisted = [
        {
            "id": uuid4(),
            "candidate_workspace_product_id": deterministic.workspace_product_id,
            "confidence": "0.80",
            "reasons": {"alias_hit": deterministic_top},
        }
    ]
    decisions: list[object] = []
    task_reasons: list[object] = []
    monkeypatch.setattr(service, "_backfill_missing_embeddings", lambda _client: None)
    monkeypatch.setattr(matching_module, "_decision_for_line", lambda *_a: None)
    monkeypatch.setattr(matching_module, "_candidate_rows", lambda *_a: [])
    for name in (
        "_deterministic_products_for_line",
        "_aliases_for_line",
        "_supplier_code_aliases_for_line",
    ):
        monkeypatch.setattr(matching_module, name, lambda *_a: [])
    monkeypatch.setattr(matching_module, "find_deterministic_candidate", lambda **_k: deterministic)
    # This can be our deterministic set or another runner's non-deterministic
    # set returned by the atomic insert's conflict reload.
    monkeypatch.setattr(service, "_persist_candidates", lambda *_a: persisted)
    monkeypatch.setattr(
        service,
        "_create_automatic_decision",
        lambda _client, _member, _line, candidate, **_k: decisions.append(candidate),
    )
    monkeypatch.setattr(
        service, "_create_task", lambda *_a, **kwargs: task_reasons.append(kwargs["reason"])
    )
    service._ensure_pipeline(  # noqa: SLF001
        client=object(),
        member=member,
        quote={"id": line["quotation_id"]},
        lines=[line],
        bearer_token="caller-token",
    )
    if deterministic_top:
        assert decisions == persisted
        assert task_reasons == []
    else:
        assert decisions == []
        assert task_reasons == ["low_confidence"]
