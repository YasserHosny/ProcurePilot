"""Integration tests for the R4.2 Grounded Procurement Analyst API (T010).

Tests one question per FR-002 category against the HTTP layer using the
TestClient + mocked AnalystService pattern (consistent with test_forecasting_api.py).
Also tests the unsupported-question case.

Confirms:
- Each supported category gets a cited, g3_unmet answer.
- An unsupported question gets an explicit refusal, no citations.
- The endpoint requires Idempotency-Key.
- Any active member may call the endpoint (no role restriction — FR-009).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.analyst.schemas import (
    AnalystCategory,
    AnalystCitationResponse,
    AnalystConversationResponse,
    AnalystTurnResponse,
    CalculationDetail,
    CitationSourceKind,
)
from procurepilot_api.modules.analyst.service import AnalystService, get_analyst_service
from procurepilot_api.modules.auth.jwt import MemberRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _member(role: MemberRole = MemberRole.buyer) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="test@example.com",
        role=role,
    )


def _make_conversation_response(
    question: str,
    category: AnalystCategory,
    answer_text: str,
    with_citation: bool = True,
    with_calculation: bool = True,
) -> AnalystConversationResponse:
    now = datetime.now(UTC)
    conv_id = uuid4()
    turn_id = uuid4()
    citations = []
    if with_citation:
        citations = [
            AnalystCitationResponse(
                id=uuid4(),
                turn_id=turn_id,
                source_kind=CitationSourceKind.purchase_order,
                source_id=uuid4(),
                created_at=now,
            )
        ]
    calculation = None
    if with_calculation:
        calculation = CalculationDetail(
            inputs=[{"spend_records": 1}],
            formula="sum of spend amounts",
            result=None,
        )
    turn = AnalystTurnResponse(
        id=turn_id,
        conversation_id=conv_id,
        creating_member_id=uuid4(),
        question_text=question,
        category=category,
        answer_text=answer_text,
        calculation_version="analyst-retrieval-v1",
        release_posture="g3_unmet",
        calculation=calculation,
        citations=citations,
        next_step_url=None,
        created_at=now,
    )
    return AnalystConversationResponse(
        id=conv_id,
        tenant_id=uuid4(),
        creating_member_id=uuid4(),
        created_at=now,
        turns=[turn],
    )


def _make_refusal_response(question: str) -> AnalystConversationResponse:
    now = datetime.now(UTC)
    conv_id = uuid4()
    turn = AnalystTurnResponse(
        id=uuid4(),
        conversation_id=conv_id,
        creating_member_id=uuid4(),
        question_text=question,
        category=AnalystCategory.spend_savings,
        answer_text=(
            "I can't answer that question yet. This analyst only supports questions about "
            "spend and savings, supplier performance and risk, order and quotation history, "
            "and reorder forecasts."
        ),
        calculation_version="analyst-retrieval-v1",
        release_posture="g3_unmet",
        calculation=None,
        citations=[],
        next_step_url=None,
        created_at=now,
    )
    return AnalystConversationResponse(
        id=conv_id,
        tenant_id=uuid4(),
        creating_member_id=uuid4(),
        created_at=now,
        turns=[turn],
    )


def _make_client(member: CurrentMember, service: AnalystService) -> TestClient:
    app = create_app()
    app.dependency_overrides[bearer_token] = lambda: "tok"
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[get_analyst_service] = lambda: service
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# T010: One question per FR-002 category
# ---------------------------------------------------------------------------


def test_spend_savings_question_returns_cited_answer() -> None:
    """spend_savings: POST returns 201 with a turn containing citations and g3_unmet."""
    question = "How much have we spent this year?"
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.spend_savings,
        answer_text="Total spend: SAR 12,345.00 across 5 record(s).",
        with_citation=True,
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    member = _member(MemberRole.buyer)
    client = _make_client(member, service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "turns" in body
    assert len(body["turns"]) == 1
    turn = body["turns"][0]
    assert turn["release_posture"] == "g3_unmet"
    assert turn["calculation_version"] == "analyst-retrieval-v1"
    assert len(turn["citations"]) == 1


def test_supplier_performance_risk_question_returns_cited_answer() -> None:
    """supplier_performance_risk: POST returns 201 with a cited turn."""
    question = "What is the risk level for our suppliers?"
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.supplier_performance_risk,
        answer_text="Supplier risk summary: Acme: risk_level=high, score=0.78.",
        with_citation=True,
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["turns"][0]["release_posture"] == "g3_unmet"


def test_orders_quotations_question_returns_cited_answer() -> None:
    """orders_quotations: POST returns 201 with a cited turn."""
    question = "Show me our purchase orders."
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.orders_quotations,
        answer_text="Order and quotation summary: 3 order(s).",
        with_citation=True,
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
    assert resp.json()["turns"][0]["release_posture"] == "g3_unmet"


def test_reorder_forecasts_question_returns_cited_answer() -> None:
    """reorder_forecasts: POST returns 201 with a cited turn."""
    question = "Which products need reordering?"
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.reorder_forecasts,
        answer_text="2 reorder proposal(s) found.",
        with_citation=True,
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
    assert resp.json()["turns"][0]["release_posture"] == "g3_unmet"


def test_unsupported_question_returns_explicit_refusal() -> None:
    """FR-002: an unsupported question must get an explicit refusal, never a guess.
    The refusal turn has no citations and a clearly-worded refusal answer.
    """
    question = "What is the weather like today?"
    expected = _make_refusal_response(question)
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
    body = resp.json()
    turn = body["turns"][0]
    assert turn["citations"] == [], "Unsupported answer must have no citations"
    answer_lower = turn["answer_text"].lower()
    assert "can't answer" in answer_lower or "only supports" in answer_lower, (
        f"Expected explicit refusal, got: {turn['answer_text']!r}"
    )


# ---------------------------------------------------------------------------
# Idempotency-Key enforcement
# ---------------------------------------------------------------------------


def test_missing_idempotency_key_returns_422() -> None:
    """The endpoint must reject requests without Idempotency-Key."""
    service = MagicMock(spec=AnalystService)
    client = _make_client(_member(), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": "How much have we spent?"},
        # No Idempotency-Key header
    )

    assert resp.status_code == 422
    service.ask.assert_not_called()


# ---------------------------------------------------------------------------
# Role access: any active member may call the endpoint (FR-009)
# ---------------------------------------------------------------------------


def test_viewer_can_ask_a_question() -> None:
    """FR-009: even a viewer role may ask a question (no role restriction on this mutation)."""
    question = "How much have we spent?"
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.spend_savings,
        answer_text="Total spend: SAR 1,000.00 across 1 record(s).",
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(MemberRole.viewer), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201


def test_branch_manager_can_ask_a_question() -> None:
    """FR-009: branch_manager role may also ask a question."""
    question = "What is our reorder status?"
    expected = _make_conversation_response(
        question=question,
        category=AnalystCategory.reorder_forecasts,
        answer_text="1 reorder proposal(s) found.",
    )
    service = MagicMock(spec=AnalystService)
    service.ask.return_value = expected
    client = _make_client(_member(MemberRole.branch_manager), service)

    resp = client.post(
        "/api/v1/analyst/conversations",
        json={"question_text": question},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert resp.status_code == 201
