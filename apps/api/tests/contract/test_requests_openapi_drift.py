from __future__ import annotations

from pathlib import Path

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


def _contract_text() -> str:
    repo_root = Path(__file__).resolve().parents[4]
    contract = repo_root / "specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml"
    return contract.read_text(encoding="utf-8")


def test_every_contract_path_is_declared_under_requests_or_approvals() -> None:
    """A structural check on the contract itself, true from the moment it was written — not yet
    a live-route check, since Phase 2 (T009-T014) lands only the module skeleton and two
    pure-function cores (routing, valuation), no HTTP endpoints yet to compare against.

    As each user story lands its own endpoints (T020's POST/GET/PATCH /requests and
    submit/withdraw, T027's GET /approvals/pending and approve/reject, T036's threshold-rule and
    delegation CRUD), extend this file with `create_app().routes`-based assertions the same way
    R2.0's test_organisation_openapi_drift.py grew alongside its own user stories — see that
    file for the exact pattern (`{route.path for route in create_app().routes}` compared against
    `/api/v1` + each CONTRACT_PATHS entry)."""
    text = _contract_text()
    for path in CONTRACT_PATHS:
        assert f"  {path}:" in text, f"{path} missing from the contract"
        assert path.startswith("/requests") or path.startswith("/approvals")
