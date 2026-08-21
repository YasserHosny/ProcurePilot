from __future__ import annotations

from pathlib import Path

from procurepilot_api.main import create_app


def test_smart_compare_routes_match_contract_paths() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    contract = (
        repo_root
        / "specs/005-smart-compare-intelligence/contracts/offers-and-baskets.openapi.yaml"
    )
    text = contract.read_text(encoding="utf-8")
    app_paths = {route.path for route in create_app().routes}
    for path in [
        "/api/v1/offers",
        "/api/v1/offers/compare",
        "/api/v1/products/{product_id}/price-history",
        "/api/v1/baskets/optimise",
        "/api/v1/baskets/{id}",
        "/api/v1/alerts",
        "/api/v1/alerts/{id}/dismiss",
    ]:
        assert path in app_paths
    for contract_path in [
        "/offers:",
        "/offers/compare:",
        "/products/{product_id}/price-history:",
        "/baskets/optimise:",
        "/baskets/{id}:",
        "/alerts:",
        "/alerts/{id}/dismiss:",
    ]:
        assert contract_path in text
