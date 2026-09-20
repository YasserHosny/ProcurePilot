from procurepilot_api.main import create_app


def test_partner_api_is_read_only_and_uses_expected_paths() -> None:
    app = create_app()
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in app.routes}
    openapi = app.openapi()

    assert ("/api/v1/partner/orders", ("GET",)) in paths
    assert ("/api/v1/partner/orders/{order_id}", ("GET",)) in paths
    assert ("/api/v1/partner/catalogue/products", ("GET",)) in paths
    assert not any(
        path.startswith("/api/v1/partner/") and "POST" in methods for path, methods in paths
    )
    assert all(
        parameter.get("name") != "tenant_id"
        for path, operation in openapi["paths"].items()
        if path.startswith("/api/v1/partner/")
        for parameter in operation.get("parameters", [])
    )
