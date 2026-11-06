from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unit.test_approval_decisions import member

from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.errors import register_exception_handlers
from procurepilot_api.modules.requests.router import router
from procurepilot_api.modules.requests.schemas import (
    BulkApprovalDecisionResponse,
    BulkApprovalDecisionResult,
)
from procurepilot_api.modules.requests.service import RequestsService, get_requests_service


@pytest.fixture
def service() -> Mock:
    return Mock(spec=RequestsService)


@pytest.fixture
def client(service: Mock) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[bearer_token] = lambda: "verified-token"
    app.dependency_overrides[current_member] = member
    app.dependency_overrides[get_requests_service] = lambda: service
    return TestClient(app)


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "approved", "request_ids": []},
        {"decision": "approved", "request_ids": [str(uuid4()) for _ in range(26)]},
        {"decision": "approved", "request_ids": ["11111111-1111-4111-8111-111111111111"] * 2},
        {"decision": "approved", "request_ids": ["bad-id"]},
        {"decision": "invalid", "request_ids": [str(uuid4())]},
        {"decision": "rejected", "request_ids": [str(uuid4())]},
        {"decision": "rejected", "comment": " \t", "request_ids": [str(uuid4())]},
        {"decision": "approved", "comment": "x" * 2001, "request_ids": [str(uuid4())]},
    ],
)
def test_invalid_body_is_422_without_any_item_run(
    client: TestClient, service: Mock, body: dict
) -> None:
    response = client.post(
        "/api/v1/approvals/bulk-decisions", json=body, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 422, response.text
    service.bulk_decisions.assert_not_called()


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": "invalid"}])
def test_batch_key_is_required_uuid(client: TestClient, service: Mock, headers: dict) -> None:
    response = client.post(
        "/api/v1/approvals/bulk-decisions",
        headers=headers,
        json={"decision": "approved", "request_ids": [str(uuid4())]},
    )
    assert response.status_code == 422, response.text
    service.bulk_decisions.assert_not_called()


def test_valid_batch_returns_200_even_if_all_items_fail(client: TestClient, service: Mock) -> None:
    rid, key = uuid4(), uuid4()
    service.bulk_decisions.return_value = BulkApprovalDecisionResponse(
        results=[
            BulkApprovalDecisionResult(request_id=rid, outcome="failed", error_code="not_found")
        ],
        decided_count=0,
        failed_count=1,
    )
    response = client.post(
        "/api/v1/approvals/bulk-decisions",
        headers={"Idempotency-Key": str(key)},
        json={"decision": "approved", "request_ids": [str(rid)]},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "results": [
            {
                "request_id": str(rid),
                "outcome": "failed",
                "error_code": "not_found",
                "request": None,
            }
        ],
        "decided_count": 0,
        "failed_count": 1,
    }
    call = service.bulk_decisions.call_args.kwargs
    assert call["idempotency_key"] == key
    assert call["bearer_token"] == "verified-token"
    assert call["payload"].request_ids == [rid]


def test_bulk_openapi_matches_documented_bounds_and_required_header() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    live = app.openapi()
    contract = yaml.safe_load(
        (
            Path(__file__).resolve().parents[4]
            / "specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml"
        ).read_text()
    )
    for document, path in [
        (live, "/api/v1/approvals/bulk-decisions"),
        (contract, "/approvals/bulk-decisions"),
    ]:
        operation = document["paths"][path]["post"]
        header = next(p for p in operation["parameters"] if p.get("name") == "Idempotency-Key")
        assert header["required"] is True
        assert header["schema"]["format"] == "uuid"
        assert operation["requestBody"]["required"] is True
        assert operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/BulkApprovalDecisionResponse")
        schema = document["components"]["schemas"]["BulkApprovalDecisionInput"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {"decision", "request_ids"}
        ids = schema["properties"]["request_ids"]
        assert ids["minItems"] == 1 and ids["maxItems"] == 25
        assert ids["items"]["format"] == "uuid"
        assert schema["properties"]["decision"]["enum"] == ["approved", "rejected"]
        assert set(
            document["components"]["schemas"]["BulkApprovalDecisionResponse"]["required"]
        ) == {"results", "decided_count", "failed_count"}
