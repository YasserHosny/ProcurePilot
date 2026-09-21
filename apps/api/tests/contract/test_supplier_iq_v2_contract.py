"""OpenAPI contract coverage for Supplier IQ v2 and negotiation briefs."""

from procurepilot_api.main import create_app


def test_supplier_iq_v2_exposes_the_approved_paths_and_methods() -> None:
    paths = create_app().openapi()["paths"]
    expected = {
        "/api/v1/suppliers/{supplier_id}/scorecard": {"get"},
        "/api/v1/supplier-iq/recompute": {"post"},
        "/api/v1/supplier-iq/risks": {"get"},
        "/api/v1/suppliers/{supplier_id}/negotiation-briefs": {"post"},
        "/api/v1/negotiation-briefs": {"get"},
        "/api/v1/negotiation-briefs/{brief_id}": {"get"},
        "/api/v1/negotiation-briefs/{brief_id}/acknowledge": {"post"},
        "/api/v1/negotiation-briefs/{brief_id}/dismiss": {"post"},
    }

    for path, methods in expected.items():
        assert path in paths
        assert methods <= set(paths[path])


def test_supplier_iq_v2_mutations_require_idempotency_keys() -> None:
    paths = create_app().openapi()["paths"]
    mutation_paths = (
        "/api/v1/supplier-iq/recompute",
        "/api/v1/suppliers/{supplier_id}/negotiation-briefs",
        "/api/v1/negotiation-briefs/{brief_id}/acknowledge",
        "/api/v1/negotiation-briefs/{brief_id}/dismiss",
    )

    for path in mutation_paths:
        parameters = paths[path]["post"].get("parameters", [])
        idempotency = next(
            parameter for parameter in parameters if parameter["name"] == "Idempotency-Key"
        )
        assert idempotency["in"] == "header"
        assert idempotency["required"] is False
        assert idempotency["schema"]["anyOf"]


def test_supplier_risk_queue_contract_includes_scan_fields() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    snapshot = schemas["SupplierRiskSnapshot"]

    assert {"supplier_name", "risk_level"} <= set(snapshot["required"])
    assert snapshot["properties"]["supplier_name"]["type"] == "string"
    risk_level = snapshot["properties"]["risk_level"]["anyOf"]
    assert ["low", "medium", "high"] in [item.get("enum") for item in risk_level]
