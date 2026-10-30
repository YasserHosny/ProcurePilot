from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching import service as matching
from procurepilot_api.modules.matching.schemas import ProductSummary


@pytest.mark.parametrize(
    "measured", [{}, {"lexical_similarity": "0.8123", "brand_match": "0.0000"}]
)
@pytest.mark.parametrize("endpoint", ["task", "quotation"])
def test_candidate_measured_map_survives_detail_endpoint(
    monkeypatch: pytest.MonkeyPatch, measured: dict[str, str], endpoint: str
) -> None:
    line_id, quotation_id, product_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    line = {
        "id": line_id,
        "quotation_id": quotation_id,
        "line_number": 1,
        "original_text": "Supplier wording",
    }
    task = {
        "id": uuid4(),
        "quotation_line_id": line_id,
        "status": "open",
        "priority": "normal",
        "reason": "low_confidence",
        "created_at": now,
    }
    candidate = {
        "id": uuid4(),
        "quotation_line_id": line_id,
        "candidate_workspace_product_id": product_id,
        "confidence": "0.4700",
        "rank": 1,
        "created_at": now,
        "reasons": {
            "alias_hit": False,
            "gtin_match": False,
            "supplier_code_match": False,
            "measured": measured,
        },
    }
    product = ProductSummary(
        id=product_id,
        tenant_name="Product",
        canonical_name="Product",
        base_unit="litre",
        status="active",
    )
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    # Replace storage boundaries, exercising the real candidate/task serializers and routes.
    monkeypatch.setattr(matching, "authenticated_client", lambda *_: object())
    monkeypatch.setattr(matching, "_line_row", lambda *_: line)
    monkeypatch.setattr(matching, "_line_rows", lambda *_: [line])
    monkeypatch.setattr(
        matching, "_quotation_row", lambda *_: {"id": quotation_id, "status": "reviewed"}
    )
    monkeypatch.setattr(matching, "_latest_task_for_line", lambda *_: task)
    monkeypatch.setattr(matching, "_open_task_for_line", lambda *_: task)
    monkeypatch.setattr(matching, "_open_task_count", lambda *_: 1)
    monkeypatch.setattr(matching, "_decision_for_line", lambda *_: None)
    monkeypatch.setattr(matching, "_candidate_rows", lambda *_: [candidate])
    monkeypatch.setattr(matching, "_product_summary", lambda *_: product)
    # The quotation endpoint reads the same rows in batches.
    monkeypatch.setattr(
        matching._LineMatchState,  # noqa: SLF001
        "read",
        classmethod(
            lambda cls, *_: cls(
                candidates={str(line_id): [candidate]},
                decisions={},
                tasks={str(line_id): [task]},
            )
        ),
    )
    monkeypatch.setattr(matching, "_product_summaries", lambda *_: {str(product_id): product})
    service = matching.MatchingService()
    monkeypatch.setattr(service, "_ensure_pipeline", lambda **_: None)
    app = create_app()
    app.dependency_overrides[bearer_token] = lambda: "buyer-token"
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[matching.get_matching_service] = lambda: service

    path = (
        f"/api/v1/quotation-lines/{line_id}/match-task"
        if endpoint == "task"
        else f"/api/v1/quotations/{quotation_id}/matches"
    )
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    if endpoint == "quotation":
        body = body["lines"][0]
        assert body["task"]["candidates"][0]["reasons"]["measured"] == measured
    assert body["candidates"][0]["reasons"]["measured"] == measured
