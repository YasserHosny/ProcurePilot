"""OpenAPI contract coverage for R4.0 forecasting and reorder proposals."""

from procurepilot_api.main import create_app


def test_forecasting_exposes_the_approved_paths_and_methods() -> None:
    paths = create_app().openapi()["paths"]
    expected = {
        "/api/v1/forecasting/recompute": {"post"},
        "/api/v1/forecasting/reorder-proposals": {"get"},
        "/api/v1/forecasting/reorder-proposals/{proposal_id}/prepare-request": {"post"},
    }

    for path, methods in expected.items():
        assert path in paths, f"Missing path: {path}"
        assert methods <= set(paths[path]), f"Missing method(s) {methods} on {path}"


def test_reorder_proposal_schema_includes_required_fields() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    proposal = schemas["ReorderProposal"]

    required = set(proposal["required"])
    assert {
        "id",
        "demand_forecast_id",
        "workspace_product_id",
        "product_name",
        "status",
        "horizon_days",
        "confidence",
        "state",
        "release_posture",
        "valid_from",
        "valid_until",
        "created_at",
    } <= required


def test_reorder_proposal_release_posture_is_g3_unmet() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    proposal = schemas["ReorderProposal"]
    posture = proposal["properties"]["release_posture"]
    # should be a const / enum that only allows "g3_unmet"
    allowed = posture.get("enum") or [posture.get("const")]
    assert "g3_unmet" in allowed


def test_recompute_response_includes_release_posture() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    response = schemas["RecomputeResponse"]
    assert "release_posture" in response["properties"]


def test_prepare_request_input_requires_branch_and_date() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    payload = schemas["PrepareRequestInput"]
    assert {"branch_id", "required_by_date"} <= set(payload["required"])


def test_prepare_request_response_includes_purchase_request_id() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    response = schemas["PrepareRequestResponse"]
    assert "purchase_request_id" in response["properties"]
    assert "proposal" in response["properties"]
