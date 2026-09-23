"""Forecasting API integration tests — RBAC and response shape (no DB required)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.auth.rbac import require_role
from procurepilot_api.modules.forecasting.schemas import (
    PrepareRequestResponse,
    RecomputeResponse,
    ReorderProposal,
    ReorderProposalList,
)
from procurepilot_api.modules.forecasting.service import (
    ForecastingService,
    get_forecasting_service,
)

WRITE_ROLES = (MemberRole.owner, MemberRole.buyer)
READ_ROLES = (
    MemberRole.owner,
    MemberRole.buyer,
    MemberRole.branch_manager,
    MemberRole.approver,
    MemberRole.viewer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _member(role: MemberRole = MemberRole.owner) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="test@example.com",
        role=role,
    )


def _proposal(tenant_id: object = None) -> ReorderProposal:
    now = datetime.now(UTC)
    return ReorderProposal(
        id=uuid4(),
        demand_forecast_id=uuid4(),
        workspace_product_id=uuid4(),
        product_name="Widget A",
        status="open",
        horizon_days=30,
        source_window_start=date.today() - timedelta(days=90),
        source_window_end=date.today(),
        observed_history_days=200,
        expected_daily_demand="1.5000",
        expected_demand="45.0000",
        uncertainty_lower="40.0000",
        uncertainty_upper="50.0000",
        stock_on_hand="10.0000",
        suggested_quantity="35.0000",
        confidence="high",
        state="ready",
        release_posture="g3_unmet",
        valid_from=now,
        valid_until=now + timedelta(days=30),
        created_at=now,
    )


def _make_client(
    member: CurrentMember,
    service: ForecastingService,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[bearer_token] = lambda: "tok"
    app.dependency_overrides[current_member] = lambda: member
    app.dependency_overrides[require_role(*WRITE_ROLES)] = lambda: member
    app.dependency_overrides[get_forecasting_service] = lambda: service
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /forecasting/reorder-proposals
# ---------------------------------------------------------------------------


def test_list_reorder_proposals_returns_200_with_items() -> None:
    proposal = _proposal()
    service = MagicMock(spec=ForecastingService)
    service.list_proposals.return_value = ReorderProposalList(
        items=[proposal], next_cursor=None
    )
    client = _make_client(_member(), service)

    resp = client.get("/api/v1/forecasting/reorder-proposals")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["release_posture"] == "g3_unmet"
    assert body["items"][0]["state"] == "ready"
    assert body["next_cursor"] is None


def test_list_reorder_proposals_passes_cursor_and_limit() -> None:
    service = MagicMock(spec=ForecastingService)
    service.list_proposals.return_value = ReorderProposalList(items=[], next_cursor=None)
    client = _make_client(_member(), service)

    client.get("/api/v1/forecasting/reorder-proposals?cursor=abc&limit=10")
    service.list_proposals.assert_called_once_with(
        bearer_token="tok", cursor="abc", limit=10
    )


def test_list_reorder_proposals_limit_capped_at_100() -> None:
    service = MagicMock(spec=ForecastingService)
    service.list_proposals.return_value = ReorderProposalList(items=[], next_cursor=None)
    client = _make_client(_member(), service)

    resp = client.get("/api/v1/forecasting/reorder-proposals?limit=999")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /forecasting/recompute
# ---------------------------------------------------------------------------


def test_recompute_returns_200_with_g3_unmet_posture() -> None:
    service = MagicMock(spec=ForecastingService)
    service.recompute.return_value = RecomputeResponse(
        generated_forecasts=3,
        open_proposals=3,
        release_posture="g3_unmet",
    )
    client = _make_client(_member(MemberRole.buyer), service)

    resp = client.post("/api/v1/forecasting/recompute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["release_posture"] == "g3_unmet"
    assert body["generated_forecasts"] == 3


def test_recompute_denied_for_viewer() -> None:
    app = create_app()
    viewer = _member(MemberRole.viewer)
    app.dependency_overrides[bearer_token] = lambda: "tok"
    app.dependency_overrides[current_member] = lambda: viewer
    # do NOT override require_role — let real RBAC run
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/v1/forecasting/recompute")
    assert resp.status_code == 403


def test_recompute_denied_for_branch_manager() -> None:
    app = create_app()
    bm = _member(MemberRole.branch_manager)
    app.dependency_overrides[bearer_token] = lambda: "tok"
    app.dependency_overrides[current_member] = lambda: bm
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/v1/forecasting/recompute")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /forecasting/reorder-proposals/{id}/prepare-request
# ---------------------------------------------------------------------------


def test_prepare_request_returns_200_with_purchase_request_id() -> None:
    proposal = _proposal()
    purchase_request_id = uuid4()
    service = MagicMock(spec=ForecastingService)
    service.prepare_request.return_value = PrepareRequestResponse(
        proposal=proposal,
        purchase_request_id=purchase_request_id,
    )
    client = _make_client(_member(), service)

    resp = client.post(
        f"/api/v1/forecasting/reorder-proposals/{proposal.id}/prepare-request",
        json={
            "branch_id": str(uuid4()),
            "required_by_date": str(date.today() + timedelta(days=7)),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["purchase_request_id"] == str(purchase_request_id)
    assert body["proposal"]["release_posture"] == "g3_unmet"


def test_prepare_request_payload_validation_rejects_missing_branch() -> None:
    service = MagicMock(spec=ForecastingService)
    client = _make_client(_member(), service)

    resp = client.post(
        f"/api/v1/forecasting/reorder-proposals/{uuid4()}/prepare-request",
        json={"required_by_date": str(date.today() + timedelta(days=7))},
    )
    assert resp.status_code == 422


def test_prepare_request_payload_rejects_extra_fields() -> None:
    """PrepareRequestInput uses StrictApiModel — extra fields are forbidden."""
    service = MagicMock(spec=ForecastingService)
    client = _make_client(_member(), service)

    resp = client.post(
        f"/api/v1/forecasting/reorder-proposals/{uuid4()}/prepare-request",
        json={
            "branch_id": str(uuid4()),
            "required_by_date": str(date.today() + timedelta(days=7)),
            "surprise_field": "hack",
        },
    )
    assert resp.status_code == 422
