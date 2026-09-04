from __future__ import annotations

from pathlib import Path

from procurepilot_api.main import create_app


def test_organisation_routes_match_contract_paths() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    contract = repo_root / "specs/007-organisation-model/contracts/organisation.openapi.yaml"
    text = contract.read_text(encoding="utf-8")
    app_paths = {route.path for route in create_app().routes}
    # This list grows as the remaining user-story endpoints land: branches, then
    # cost centres, then budgets. Extending it in those PRs is expected behaviour.
    for path in [
        "/api/v1/organisation/branch-role-assignments",
        "/api/v1/organisation/branch-role-assignments/{assignment_id}",
    ]:
        assert path in app_paths
    for contract_path in [
        "/organisation/branch-role-assignments:",
        "/organisation/branch-role-assignments/{assignment_id}:",
    ]:
        assert contract_path in text
