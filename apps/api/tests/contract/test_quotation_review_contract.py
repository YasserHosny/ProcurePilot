from __future__ import annotations

from procurepilot_api.main import create_app


def test_quotation_review_routes_are_registered() -> None:
    routes = {(route.path, ",".join(sorted(route.methods))) for route in create_app().routes}

    assert ("/api/v1/quotations/{quotation_id}", "GET") in routes
    assert ("/api/v1/quotations/{quotation_id}", "PATCH") in routes
    assert ("/api/v1/quotations/{quotation_id}/confirm", "POST") in routes
    assert ("/api/v1/review-tasks", "GET") in routes
