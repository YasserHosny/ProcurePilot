from __future__ import annotations

from procurepilot_api.main import create_app


def test_quotation_upload_extract_routes_are_registered() -> None:
    routes = {(route.path, ",".join(sorted(route.methods))) for route in create_app().routes}

    assert ("/api/v1/documents/presign", "POST") in routes
    assert ("/api/v1/documents/{document_id}", "GET") in routes
    assert ("/api/v1/quotations", "POST") in routes
    assert ("/api/v1/quotations/{quotation_id}/extract", "POST") in routes
    assert ("/api/v1/jobs/{job_id}", "GET") in routes
