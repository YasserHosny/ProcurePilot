from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unit.test_quotation_review_task_sort import SUPPLIER_IDS, FakeClient

from procurepilot_api.deps import bearer_token, current_member
from procurepilot_api.modules.quotations import service as quotation_service_module
from procurepilot_api.modules.quotations.router import router
from procurepilot_api.modules.quotations.schemas import ReviewTaskList
from procurepilot_api.modules.quotations.service import QuotationService, get_quotation_service


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    fake = FakeClient()
    monkeypatch.setattr(quotation_service_module, "authenticated_client", lambda *_: fake)
    monkeypatch.setattr(quotation_service_module, "_sync_open_review_tasks", lambda *_: None)
    return fake


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"supplier_id": UUID(SUPPLIER_IDS[0])}, ("eq", "quotation.supplier_id", SUPPLIER_IDS[0])),
        ({"reason": "line_count_mismatch"}, ("eq", "reason", "line_count_mismatch")),
        ({"quotation_status": "in_review"}, ("eq", "quotation.status", "in_review")),
    ],
)
def test_queue_filter_is_applied_in_database(
    client: FakeClient, params: dict[str, UUID | str], expected: tuple[str, str, object]
) -> None:
    QuotationService().list_review_tasks(bearer_token="dummy", **params)
    assert expected in client.review_task_query.filters
    assert client.review_task_query.orders == [("created_at", True), ("id", False)]
    assert client.review_task_query.range_args == (0, 50)


def test_filters_intersect_supplier_search_and_task_status(client: FakeClient) -> None:
    client.supplier_query.data = [{"id": value} for value in SUPPLIER_IDS]
    QuotationService().list_review_tasks(
        bearer_token="dummy",
        supplier_id=UUID(SUPPLIER_IDS[0]),
        reason="read_failure",
        quotation_status="in_review",
        search="Supplier",
        status="in_progress",
        priority="high",
    )
    assert all(
        value in client.review_task_query.filters
        for value in [
            ("in", "quotation.supplier_id", SUPPLIER_IDS),
            ("eq", "quotation.supplier_id", SUPPLIER_IDS[0]),
            ("eq", "reason", "read_failure"),
            ("eq", "quotation.status", "in_review"),
            ("eq", "status", "in_progress"),
            ("eq", "priority", "high"),
        ]
    )


@pytest.mark.parametrize("param", ["reason", "quotation_status", "supplier_id"])
def test_invalid_queue_filter_returns_422(param: str) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[bearer_token] = lambda: "dummy"
    app.dependency_overrides[current_member] = lambda: object()

    class EmptyService:
        def list_review_tasks(self, **kwargs: object) -> ReviewTaskList:
            return ReviewTaskList(items=[], next_cursor=None)

    app.dependency_overrides[get_quotation_service] = EmptyService
    with TestClient(app) as http:
        response = http.get("/api/v1/review-tasks", params={param: "unknown"})
    assert response.status_code == 422


def test_supplier_without_visible_tasks_returns_empty(client: FakeClient) -> None:
    result = QuotationService().list_review_tasks(
        bearer_token="dummy", supplier_id=UUID(SUPPLIER_IDS[1])
    )
    assert result.items == []
    assert result.next_cursor is None
    assert ("eq", "quotation.supplier_id", SUPPLIER_IDS[1]) in client.review_task_query.filters


def test_route_forwards_new_filters_and_preserves_response_shape() -> None:
    captured: dict[str, object] = {}

    class RecordingService:
        def list_review_tasks(self, **kwargs: object) -> ReviewTaskList:
            captured.update(kwargs)
            return ReviewTaskList(items=[], next_cursor=None)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[bearer_token] = lambda: "dummy"
    app.dependency_overrides[current_member] = lambda: object()
    app.dependency_overrides[get_quotation_service] = RecordingService
    with TestClient(app) as http:
        response = http.get(
            "/api/v1/review-tasks",
            params={
                "supplier_id": SUPPLIER_IDS[0],
                "reason": "total_unverified",
                "quotation_status": "refused",
                "status": "all",
                "search": "Supplier",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
    assert captured["supplier_id"] == UUID(SUPPLIER_IDS[0])
    assert captured["reason"] == "total_unverified"
    assert captured["quotation_status"] == "refused"
    assert captured["status"] == "all"
    assert captured["search"] == "Supplier"
