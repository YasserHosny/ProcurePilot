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
    # risk_level is a real Enum (RiskLevel), not a bare Literal, specifically so its ordering
    # can't be silently collapsed with an unrelated same-valued Literal (EvidenceConfidence is
    # the reverse order) — see schemas.py's own RiskLevel docstring. That means its schema entry
    # is a named $ref, not an inline enum list; resolve it before checking the documented order.
    refs = [item["$ref"] for item in risk_level if "$ref" in item]
    assert refs, f"expected risk_level to reference a named component schema, got {risk_level!r}"
    risk_level_schema = schemas[refs[0].rsplit("/", 1)[-1]]
    assert risk_level_schema["enum"] == ["low", "medium", "high"]


def test_supplier_scorecard_contract_preserves_v1_and_adds_v2_detail() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    scorecard = schemas["SupplierScorecard"]

    assert {
        "supplier_id",
        "metrics",
        "risk_score",
        "source_counts",
        "confidence",
        "insufficient_evidence",
        "computed_at",
        "rule_version",
    } <= set(scorecard["required"])
    assert {
        "snapshot_id",
        "state",
        "risk_level",
        "release_posture",
        "valid_from",
        "valid_until",
        "observed_history_days",
        "v2_risk_score",
        "v2_components",
        "v2_weights",
        "source_fingerprint",
    } <= set(scorecard["properties"])


def test_negotiation_brief_items_expose_typed_source_references() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    item = schemas["NegotiationBriefItem"]
    evidence = schemas["NegotiationBriefEvidenceRef"]

    assert "evidence" in item["properties"]
    assert {"evidence_id", "source_kind", "source_id"} <= set(evidence["required"])
