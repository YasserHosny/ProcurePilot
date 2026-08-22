from __future__ import annotations

from procurepilot_api.main import API_PREFIX, create_app


def test_value_proof_routes_are_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    expected = {
        f"{API_PREFIX}/purchases",
        f"{API_PREFIX}/savings",
        f"{API_PREFIX}/savings/{{id}}",
        f"{API_PREFIX}/savings/{{id}}/evidence",
        f"{API_PREFIX}/savings/{{id}}/verify",
        f"{API_PREFIX}/exports",
        f"{API_PREFIX}/exports/{{id}}",
        f"{API_PREFIX}/billing/account",
        f"{API_PREFIX}/billing/limits/active-catalogue-products",
    }
    assert expected <= paths
