from __future__ import annotations

from pathlib import Path

from procurepilot_api.main import create_app

CONTRACT_PATHS = [
    "/requests",
    "/requests/{request_id}",
    "/requests/{request_id}/submit",
    "/requests/{request_id}/withdraw",
    "/requests/{request_id}/approve",
    "/requests/{request_id}/reject",
    "/approvals/pending",
    "/approvals/threshold-rules",
    "/approvals/threshold-rules/{rule_id}",
    "/approvals/delegations",
    "/approvals/delegations/{delegation_id}",
]

US1_ROUTES = [
    "/api/v1/requests",
    "/api/v1/requests/{request_id}",
    "/api/v1/requests/{request_id}/submit",
    "/api/v1/requests/{request_id}/withdraw",
]


def _contract_text() -> str:
    repo_root = Path(__file__).resolve().parents[4]
    contract = (
        repo_root
        / "specs/008-requests-approvals/contracts"
        / "requests-approvals.openapi.yaml"
    )
    return contract.read_text(encoding="utf-8")


def test_every_contract_path_is_declared_under_requests_or_approvals() -> (
    None
):
    text = _contract_text()
    for path in CONTRACT_PATHS:
        assert f"  {path}:" in text, f"{path} missing from the contract"
        assert path.startswith("/requests") or path.startswith("/approvals")


def test_us1_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}
    for path in US1_ROUTES:
        assert path in app_paths, f"{path} not registered in the app"
